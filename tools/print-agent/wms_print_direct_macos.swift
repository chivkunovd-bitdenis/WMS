import CoreGraphics
import CryptoKit
import Darwin
import Foundation
import ImageIO
import SQLite3

private let port: UInt16 = UInt16(ProcessInfo.processInfo.environment["WMS_PRINT_PORT"] ?? "") ?? 17843
private let localOrigin = "http://127.0.0.1:\(port)"
private let allowedOrigins: Set<String> = [
    localOrigin,
    "https://sellerfocus.pro",
    "https://www.sellerfocus.pro",
    "https://wms.sellerfocus.pro",
    "https://web-production-9e7c1.up.railway.app",
]
private let pngPrefix = Data([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
private let appName = "WMS Print Direct"
private let maxPixels: UInt64 = 40_000_000
// The browser gives up after 30 s; the answer must come earlier.  lp itself
// normally returns at once, 20 s + SIGKILL grace stays below the browser limit.
private let lpTimeout: TimeInterval = 20
/// One deadline per request, shorter than the 30 s the browser waits.
private let requestBudget: TimeInterval = 25
/// A job is never started when less than this is left of the budget.
private let minimumToStart: TimeInterval = 6
private var legacyBusyMs: Int32 = 2000
private let unknownOutcomeText = "Исход печати неизвестен: задание уже отправлялось на принтер. Проверьте принтер; повтор автоматически не отправлен."
private let inProgressText = "Это задание уже в работе, исход пока неизвестен. Проверьте принтер; повтор автоматически не отправлен."
private let closeOldText = "Закройте старую версию WMS Print и повторите."

/// Build id shown by /health; a second start compares it with the running copy.
private let buildID: String = {
    guard let executable = Bundle.main.executableURL,
          let data = try? Data(contentsOf: executable.deletingLastPathComponent().appendingPathComponent("build.json")),
          let value = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
          let commit = value["source_commit"] as? String, !commit.isEmpty else { return "dev" }
    return commit
}()

private enum PrintError: Error, CustomStringConvertible {
    case message(String)
    /// Proven: nothing reached the OS print system, so the same key may be retried.
    case notSent(String)

    var description: String {
        switch self {
        case .message(let value), .notSent(let value): return value
        }
    }
}

private struct StoredJob: Codable {
    let hash: String
    var receipt: String?
}

private struct ProcessResult {
    let status: Int32
    let output: String
    let timedOut: Bool
}

private final class OutputBuffer {
    private let lock = NSLock()
    private var data = Data()
    func append(_ chunk: Data) { lock.lock(); data.append(chunk); lock.unlock() }
    var text: String { lock.lock(); defer { lock.unlock() }; return String(data: data, encoding: .utf8) ?? "" }
}

/// Runs a system tool with a hard time limit.  Output is drained while the tool
/// runs (a full pipe cannot stall it); a tool that ignores SIGTERM is killed.
private func run(_ executable: String, _ arguments: [String], timeout: TimeInterval,
                 grace: TimeInterval = 2) throws -> ProcessResult {
    let process = Process()
    let pipe = Pipe()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    process.environment = ProcessInfo.processInfo.environment.merging(["LC_ALL": "C"]) { _, new in new }
    process.standardOutput = pipe
    process.standardError = pipe
    let exited = DispatchSemaphore(value: 0)
    process.terminationHandler = { _ in exited.signal() }
    do { try process.run() } catch {
        throw PrintError.notSent("Не удалось запустить системную печать macOS (\(executable))")
    }
    let buffer = OutputBuffer()
    let drained = DispatchSemaphore(value: 0)
    let reader = pipe.fileHandleForReading
    Thread.detachNewThread {
        while true {
            let chunk = reader.availableData
            if chunk.isEmpty { break }
            buffer.append(chunk)
        }
        drained.signal()
    }
    var timedOut = false
    if exited.wait(timeout: .now() + timeout) == .timedOut {
        timedOut = true
        process.terminate()
        if exited.wait(timeout: .now() + grace) == .timedOut {
            kill(process.processIdentifier, SIGKILL)
            _ = exited.wait(timeout: .now() + grace)
        }
    }
    // A grandchild may keep the pipe open; do not wait for it for long.
    _ = drained.wait(timeout: .now() + 1)
    return ProcessResult(status: process.isRunning ? -1 : process.terminationStatus,
                         output: buffer.text, timedOut: timedOut)
}

private func defaultPrinter(timeout: TimeInterval = 10) throws -> String {
    let result = try run("/usr/bin/lpstat", ["-d"], timeout: max(1, min(10, timeout)))
    guard !result.timedOut, result.status == 0, let separator = result.output.firstIndex(of: ":") else {
        throw PrintError.message("В системе не выбран принтер по умолчанию")
    }
    let name = result.output[result.output.index(after: separator)...].trimmingCharacters(in: .whitespacesAndNewlines)
    guard !name.isEmpty, name.count <= 127, !name.contains(where: { $0.isNewline }) else {
        throw PrintError.message("В системе не выбран принтер по умолчанию")
    }
    return name
}

private func parseReceipt(_ output: String, queue: String) -> String? {
    let pattern = NSRegularExpression.escapedPattern(for: queue) + "-[0-9]+"
    guard let expression = try? NSRegularExpression(pattern: pattern),
          let match = expression.firstMatch(
              in: output, range: NSRange(output.startIndex..., in: output)
          ),
          let range = Range(match.range, in: output) else { return nil }
    return String(output[range])
}

private func readUInt32(_ data: Data, _ offset: Int) -> UInt64 {
    data[offset..<offset + 4].reduce(UInt64(0)) { $0 << 8 | UInt64($1) }
}

/// Decodes the whole PNG before anything is marked as sent.  Opaque labels are
/// passed on byte for byte; a label with transparency is painted on white.
private func preparePNG(_ data: Data) throws -> Data {
    let invalid = PrintError.message("Ожидается корректная PNG-этикетка")
    let end = Data([0, 0, 0, 0, 0x49, 0x45, 0x4e, 0x44, 0xae, 0x42, 0x60, 0x82])  // IEND: the stream is not cut short
    guard data.count >= 45, data.starts(with: pngPrefix), data[12..<16] == Data("IHDR".utf8),
          data.suffix(12) == end else { throw invalid }
    let width = readUInt32(data, 16), height = readUInt32(data, 20)
    guard width > 0, height > 0, width * height <= maxPixels else { throw invalid }
    var hasAlpha = data[25] == 4 || data[25] == 6
    var offset = 8
    while !hasAlpha, offset + 12 <= data.count {
        let length = Int(readUInt32(data, offset))
        let type = String(data: data[offset + 4..<offset + 8], encoding: .ascii) ?? ""
        if type == "tRNS" { hasAlpha = true }
        if type == "IDAT" { break }
        offset += 12 + length
    }
    guard let source = CGImageSourceCreateWithData(data as CFData, nil), CGImageSourceGetCount(source) >= 1,
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
          CGImageSourceGetStatusAtIndex(source, 0) == .statusComplete,
          let space = CGColorSpace(name: CGColorSpace.sRGB) else { throw invalid }
    let info = CGImageAlphaInfo.noneSkipLast.rawValue
    if !hasAlpha {
        // Force the full decode: a truncated or damaged stream fails here, not in CUPS.
        guard let probe = CGContext(data: nil, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 0,
                                    space: space, bitmapInfo: info) else { throw invalid }
        probe.draw(image, in: CGRect(x: 0, y: 0, width: 1, height: 1))
        return data
    }
    guard let context = CGContext(data: nil, width: image.width, height: image.height, bitsPerComponent: 8,
                                  bytesPerRow: 0, space: space, bitmapInfo: info) else { throw invalid }
    let rect = CGRect(x: 0, y: 0, width: image.width, height: image.height)
    context.interpolationQuality = .none  // 1:1, no resampling
    context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    context.fill(rect)
    context.draw(image, in: rect)
    let output = NSMutableData()
    guard let flat = context.makeImage(),
          let destination = CGImageDestinationCreateWithData(output, "public.png" as CFString, 1, nil) else { throw invalid }
    // Keep the resolution of the source label (the new context has no DPI of its own).
    var properties: [CFString: Any] = [:]
    if let source = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any] {
        if let x = source[kCGImagePropertyDPIWidth] { properties[kCGImagePropertyDPIWidth] = x }
        if let y = source[kCGImagePropertyDPIHeight] { properties[kCGImagePropertyDPIHeight] = y }
    }
    CGImageDestinationAddImage(destination, flat, properties as CFDictionary)
    guard CGImageDestinationFinalize(destination) else { throw invalid }
    return output as Data
}

private struct LabelSize {
    let width: Double
    let height: Double
}

private func labelSize(_ body: [String: Any]) throws -> LabelSize {
    guard let width = (body["widthMm"] as? NSNumber)?.doubleValue,
          let height = (body["heightMm"] as? NSNumber)?.doubleValue,
          width >= 10, width <= 300, height >= 10, height <= 300 else {
        throw PrintError.message("WMS не передала корректный размер этикетки")
    }
    return LabelSize(width: width, height: height)
}

private func millimeters(_ value: Double) -> String {
    value.rounded() == value
        ? String(Int(value))
        : String(format: "%.2f", locale: Locale(identifier: "en_US_POSIX"), value)
}

/// The label size travels to macOS as a custom paper size (installed release 9a33b651).
private func printArguments(
    queue: String, label: String, width: Double, height: Double
) -> [String] {
    [
        "-d", queue,
        "-o", "media=Custom.\(millimeters(width))x\(millimeters(height))mm",
        "-o", "fit-to-page",
        "-o", "copies=1",
        "--", label,
    ]
}

/// The size is part of the job identity.  The first form is the one written by the
/// installed Swift release; the others are what the Python release and the oldest
/// size-less journals hold, so an old key is still recognised in every journal.
private func identityDigests(_ data: Data, _ size: LabelSize) -> (primary: String, python: String, legacy: String) {
    func sha(_ value: Data) -> String { SHA256.hash(data: value).map { String(format: "%02x", $0) }.joined() }
    var swiftIdentity = data
    swiftIdentity.append(Data("|\(size.width)x\(size.height)".utf8))
    var pythonIdentity = data
    pythonIdentity.append(Data("|\(Int((size.width * 10).rounded()))x\(Int((size.height * 10).rounded()))".utf8))
    return (sha(swiftIdentity), sha(pythonIdentity), sha(data))
}

private func submitToDefaultPrinter(_ data: Data, queue: String, size: LabelSize, deadline: Date,
                                    mark: () throws -> Void) throws -> String {
    // Everything before mark() may fail without any job in the OS.
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("wms-qr-\(UUID().uuidString)")
    do { try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true) } catch {
        throw PrintError.notSent("Не удалось подготовить файл этикетки: \(error.localizedDescription)")
    }
    defer { try? FileManager.default.removeItem(at: directory) }
    let label = directory.appendingPathComponent("label.png")
    do { try data.write(to: label, options: .atomic) } catch {
        throw PrintError.notSent("Не удалось подготовить файл этикетки: \(error.localizedDescription)")
    }
    try mark()  // the next step is the first one that can reach the OS queue
    let limit = max(2, min(lpTimeout, deadline.timeIntervalSinceNow - 4))
    let result = try run("/usr/bin/lp",
                         printArguments(queue: queue, label: label.path, width: size.width, height: size.height),
                         timeout: limit, grace: 1.5)
    guard !result.timedOut, result.status == 0 else { throw PrintError.message(unknownOutcomeText) }
    // CUPS localizes the surrounding text even with LC_ALL=C (for example,
    // "id запроса queue-123").  The queue receipt itself has a stable form.
    guard let receipt = parseReceipt(result.output, queue: queue) else {
        throw PrintError.message("macOS не подтвердила приём задания. Проверьте очередь принтера.")
    }
    return receipt
}

private enum LegacyResult {
    case ok([String: StoredJob])
    case busy
    case unreadable(String)
}

private let sqliteTransient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

private func sqliteBusy(_ code: Int32) -> Bool { [SQLITE_BUSY, SQLITE_LOCKED].contains(code & 0xff) }

/// Jobs of the previous (Python) release lived in direct-jobs.sqlite3.  Every
/// step is checked: a partial read is never taken for the whole history.
private func legacyJobs(at url: URL, busyMs: Int32) -> LegacyResult {
    var db: OpaquePointer?
    defer { sqlite3_close(db) }
    let opened = sqlite3_open_v2(url.path, &db, SQLITE_OPEN_READONLY, nil)
    guard opened == SQLITE_OK else { return sqliteBusy(opened) ? .busy : .unreadable("open \(opened)") }
    sqlite3_busy_timeout(db, busyMs)
    var statement: OpaquePointer?
    defer { sqlite3_finalize(statement) }
    let prepared = sqlite3_prepare_v2(db, "SELECT id, hash, receipt FROM jobs", -1, &statement, nil)
    guard prepared == SQLITE_OK else { return sqliteBusy(prepared) ? .busy : .unreadable("prepare \(prepared)") }
    var result: [String: StoredJob] = [:]
    var step = sqlite3_step(statement)
    while step == SQLITE_ROW {
        guard let id = sqlite3_column_text(statement, 0), let hash = sqlite3_column_text(statement, 1) else {
            return .unreadable("row")
        }
        let receipt = sqlite3_column_text(statement, 2).map { String(cString: $0) }
        result[String(cString: id)] = StoredJob(hash: String(cString: hash), receipt: receipt)
        step = sqlite3_step(statement)
    }
    guard step == SQLITE_DONE else { return sqliteBusy(step) ? .busy : .unreadable("step \(step)") }
    return .ok(result)
}

private let legacySchema = "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, hash TEXT, receipt TEXT)"

/// Writes statements into the old journal (same schema) in one transaction, so
/// that going back to the previous program still sees the history.  The wait
/// for a locked file never exceeds ``busyMs`` (the rest of the request budget).
private func legacyBatch(_ url: URL, _ operations: [(String, [String?])], busyMs: Int32, create: Bool = false) throws {
    var db: OpaquePointer?
    defer { sqlite3_close(db) }
    let flags = SQLITE_OPEN_READWRITE | (create ? SQLITE_OPEN_CREATE : 0)
    guard sqlite3_open_v2(url.path, &db, flags, nil) == SQLITE_OK else { throw PrintError.message(closeOldText) }
    sqlite3_busy_timeout(db, busyMs)
    guard sqlite3_exec(db, "BEGIN IMMEDIATE", nil, nil, nil) == SQLITE_OK else { throw PrintError.message(closeOldText) }
    var committed = false
    defer { if !committed { sqlite3_exec(db, "ROLLBACK", nil, nil, nil) } }
    for (sql, arguments) in operations {
        var statement: OpaquePointer?
        defer { sqlite3_finalize(statement) }
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else { throw PrintError.message(closeOldText) }
        for (index, value) in arguments.enumerated() {
            if let value { sqlite3_bind_text(statement, Int32(index + 1), value, -1, sqliteTransient) }
            else { sqlite3_bind_null(statement, Int32(index + 1)) }
        }
        guard sqlite3_step(statement) == SQLITE_DONE else { throw PrintError.message(closeOldText) }
    }
    guard sqlite3_exec(db, "COMMIT", nil, nil, nil) == SQLITE_OK else { throw PrintError.message(closeOldText) }
    committed = true
}

private func legacyExecute(_ url: URL, _ sql: String, _ arguments: [String?], busyMs: Int32) throws {
    try legacyBatch(url, [(sql, arguments)], busyMs: busyMs)
}

/// Milliseconds of the request budget left, capped by the normal wait for a locked file.
private func busyBudget(_ deadline: Date) -> Int32 {
    Int32(max(50, min(Double(legacyBusyMs), deadline.timeIntervalSinceNow * 1000)))
}

private final class Printer {
    private let state = NSLock()      // journals only, held for short sections
    private let printLock = NSLock()  // one OS print call at a time
    private let storeURL: URL
    private let legacyURL: URL
    private let submit: (Data, String, LabelSize, Date, () throws -> Void) throws -> String
    private let queue: (TimeInterval) throws -> String
    private var jobs: [String: StoredJob]
    private let unsentURL: URL
    private var unsent = Set<String>()     // keys proven not sent whose mark may still sit in a journal
    private let staleLock = NSLock()
    private var staleFlight = Set<String>()  // keys released without taking `state` (answer stays in time)
    private var normalized = Set<String>()  // keys whose hash was rewritten in both journals this run
    private var inflight = Set<String>()  // keys being processed right now, guarded by `state`
    private var legacyChecked = false  // the old sqlite journal was read and brought level with the json
    private var mirror = false         // marks and receipts are copied into the old journal

    init(
        directory: URL,
        submit: @escaping (Data, String, LabelSize, Date, () throws -> Void) throws -> String = submitToDefaultPrinter,
        queue: @escaping (TimeInterval) throws -> String = { try defaultPrinter(timeout: $0) }
    ) throws {
        self.submit = submit
        self.queue = queue
        self.storeURL = directory.appendingPathComponent("direct-jobs.json")
        self.legacyURL = directory.appendingPathComponent("direct-jobs.sqlite3")
        self.unsentURL = directory.appendingPathComponent("direct-unsent.json")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: storeURL.path) {
            let data = try Data(contentsOf: storeURL)
            do {
                self.jobs = try JSONDecoder().decode([String: StoredJob].self, from: data)
            } catch {
                throw PrintError.message("Журнал WMS Print повреждён; печать остановлена, чтобы не создать дубли")
            }
        } else {
            self.jobs = [:]
        }
        if let saved = try? Data(contentsOf: unsentURL), let keys = try? JSONDecoder().decode([String].self, from: saved) {
            unsent = Set(keys)
        }
        // A locked old journal must not stop the program; it stops printing instead
        // (see printJob) until the old copy is closed and the journal can be read.
        do { try importLegacy(busyMs: legacyBusyMs) } catch { fputs("\(error)\n", stderr) }
    }

    /// "Proven not sent" is kept in a small file independent of the journals, so it
    /// survives a restart: a mark without receipt and with this sign is a free key.
    private func writeUnsent() {
        if let data = try? JSONEncoder().encode(unsent.sorted()) { try? data.write(to: unsentURL, options: .atomic) }
    }

    /// Takes the mark of a proven-unsent job out of the json and the old journal.  Called
    /// with `state` held.  If a journal cannot be cleaned now, the sign stays.
    private func retractLocked(_ key: String) {
        unsent.insert(key)
        writeUnsent()
        jobs[key] = nil
        var clean = (try? persist()) != nil
        if mirror {
            clean = clean && (try? legacyExecute(legacyURL, "DELETE FROM jobs WHERE id=? AND receipt IS NULL", [key], busyMs: 2000)) != nil
        }
        if clean { unsent.remove(key); writeUnsent() }
    }

    /// Forgets that the key is being processed, within the request budget; if `state` is
    /// not free in time the next journal access does it, the answer is not delayed.
    private func releaseKey(_ key: String, deadline: Date) {
        if state.lock(before: deadline) {
            inflight.remove(key)
            state.unlock()
        } else {
            staleLock.lock()
            staleFlight.insert(key)
            staleLock.unlock()
        }
    }

    private func persist() throws {
        try JSONEncoder().encode(jobs).write(to: storeURL, options: .atomic)
    }

    /// The old sqlite journal (created when missing, same schema) and the json are
    /// brought level in both directions, so going back to the Python build still
    /// sees every key.  Locked file: error, nothing is printed.  Damaged file:
    /// warning, work goes on without the mirror.
    private func importLegacy(busyMs: Int32) throws {
        guard !legacyChecked else { return }
        if !FileManager.default.fileExists(atPath: legacyURL.path) {
            do { try legacyBatch(legacyURL, [(legacySchema, [])], busyMs: busyMs, create: true) } catch {
                fputs("Старый журнал direct-jobs.sqlite3 не создан; печать идёт без него\n", stderr)
                legacyChecked = true
                return
            }
        }
        switch legacyJobs(at: legacyURL, busyMs: busyMs) {
        case .busy:
            throw PrintError.message(closeOldText)
        case .unreadable(let reason):
            fputs("Старый журнал direct-jobs.sqlite3 не читается (\(reason)); импорт пропущен\n", stderr)
            legacyChecked = true
        case .ok(let old):
            let stale = old.keys.filter { old[$0]?.receipt == nil && unsent.contains($0) }  // proven not sent
            let fresh = old.keys.filter { jobs[$0] == nil && !stale.contains($0) }
            for key in fresh { jobs[key] = old[key] }
            if !stale.isEmpty {
                let removals = stale.map { ("DELETE FROM jobs WHERE id=? AND receipt IS NULL", [$0] as [String?]) }
                if (try? legacyBatch(legacyURL, removals, busyMs: busyMs)) != nil {
                    for key in stale { unsent.remove(key) }
                    writeUnsent()
                }
            }
            if !fresh.isEmpty {
                do { try persist() } catch {
                    for key in fresh { jobs[key] = nil }
                    throw PrintError.message("Не удалось сохранить журнал WMS Print: \(error.localizedDescription)")
                }
            }
            // The other direction: keys known only to the json (or with a newer receipt).
            var operations: [(String, [String?])] = []
            for (key, job) in jobs {
                if let known = old[key] {
                    if known.receipt == nil, let receipt = job.receipt {
                        operations.append(("UPDATE jobs SET receipt=? WHERE id=?", [receipt, key]))
                    }
                } else {
                    operations.append(("INSERT OR IGNORE INTO jobs VALUES (?, ?, ?)", [key, job.hash, job.receipt]))
                }
            }
            if !operations.isEmpty { try legacyBatch(legacyURL, operations, busyMs: busyMs) }
            legacyChecked = true
            mirror = true
        }
    }

    func printJob(_ body: [String: Any], deadline: Date = Date().addingTimeInterval(requestBudget)) throws -> String {
        guard let key = body["idempotencyKey"] as? String, (1...200).contains(key.count),
              let image = body["imageDataUrl"] as? String else {
            throw PrintError.message("Некорректное задание печати")
        }
        let prefix = "data:image/png;base64,"
        guard image.hasPrefix(prefix), let data = Data(base64Encoded: String(image.dropFirst(prefix.count))),
              data.count <= 4_000_000, data.starts(with: pngPrefix) else {
            throw PrintError.message("Ожидается корректная PNG-этикетка")
        }
        let size = try labelSize(body)
        let digests = identityDigests(data, size)
        let digest = digests.primary

        // The key's own history is answered first, never behind the print queue.  A new
        // key is registered as "in progress" at once: a parallel repeat gets "unknown".
        if let known = try knownResult(key, digests, deadline: deadline) { return known }
        defer { releaseKey(key, deadline: deadline) }
        guard printLock.lock(before: deadline) else {
            throw PrintError.message("Принтер занят предыдущим заданием. Это задание не отправлялось; повторите.")
        }
        defer { printLock.unlock() }
        guard deadline.timeIntervalSinceNow > minimumToStart else {
            throw PrintError.message("Время ожидания истекло. Это задание не отправлялось; повторите.")
        }

        // Anything below that fails before mark() leaves no trace: the key can be retried.
        let ready = try preparePNG(data)
        let queue = try queue(deadline.timeIntervalSinceNow)
        var marked = false
        let mark = { [self] in
            state.lock()
            defer { state.unlock() }
            guard deadline.timeIntervalSinceNow > minimumToStart else {
                throw PrintError.notSent("Время ожидания истекло. Это задание не отправлялось; повторите.")
            }
            let reuse = unsent.contains(key)  // a stale mark of this key is replaced
            if reuse { unsent.remove(key); writeUnsent() }
            jobs[key] = StoredJob(hash: digest, receipt: nil)
            do {
                try persist()
                if mirror {
                    // The Python release reads this journal with its own identity formula.
                    try legacyExecute(legacyURL, reuse ? "INSERT OR REPLACE INTO jobs VALUES (?, ?, NULL)"
                                                       : "INSERT OR IGNORE INTO jobs VALUES (?, ?, NULL)",
                                      [key, digests.python], busyMs: busyBudget(deadline))
                }
            } catch {
                retractLocked(key)  // not recorded everywhere, not sent
                if error is PrintError { throw PrintError.notSent("\(error). Задание не отправлялось.") }
                throw PrintError.notSent("Не удалось записать журнал печати; задание не отправлялось")
            }
            // Waiting for the journal may have used up the budget: then the job is not sent.
            guard deadline.timeIntervalSinceNow > minimumToStart else {
                retractLocked(key)
                throw PrintError.notSent("Время ожидания истекло. Это задание не отправлялось; повторите.")
            }
            marked = true
        }
        let receipt: String
        do {
            receipt = try submit(ready, queue, size, deadline, mark)
        } catch PrintError.notSent(let reason) {
            if marked {
                state.lock()
                retractLocked(key)
                state.unlock()
            }
            throw PrintError.message(reason)
        }
        state.lock()
        defer { state.unlock() }
        jobs[key] = StoredJob(hash: digest, receipt: receipt)
        // The job is already in the OS queue; a failed write must not report it as lost.
        do { try persist() } catch { fputs("Квитанция не записана в журнал: \(error)\n", stderr) }
        if mirror {
            do { try legacyExecute(legacyURL, "UPDATE jobs SET receipt=? WHERE id=?", [receipt, key], busyMs: 2000) }
            catch { fputs("Квитанция не записана в старый журнал: \(error)\n", stderr) }
        }
        return receipt
    }

    /// A stored receipt, an error for a possibly-sent or in-progress job, or nil for a new
    /// key (which is registered as in progress under the same lock).
    private func knownResult(_ key: String, _ digests: (primary: String, python: String, legacy: String),
                             deadline: Date) throws -> String? {
        guard state.lock(before: deadline) else {
            throw PrintError.message("Время ожидания истекло. Это задание не отправлялось; повторите.")
        }
        defer { state.unlock() }
        staleLock.lock()
        inflight.subtract(staleFlight)
        staleFlight.removeAll()
        staleLock.unlock()
        try importLegacy(busyMs: busyBudget(deadline))  // retried until the old journal has been read
        if jobs[key]?.receipt == nil, unsent.contains(key) { jobs[key] = nil }  // proven not sent: the key is free
        if let old = jobs[key] {
            guard [digests.primary, digests.python, digests.legacy].contains(old.hash) else { throw PrintError.message("Содержимое этого задания изменилось") }
            // The request is confirmed (same PNG and size), so each journal gets the hash in
            // the form its own reader expects; the previous version then recognises the key.
            if !normalized.contains(key) {
                if old.hash != digests.primary {
                    jobs[key] = StoredJob(hash: digests.primary, receipt: old.receipt)
                    do { try persist() } catch { jobs[key] = old; fputs("Хэш задания не обновлён в журнале: \(error)\n", stderr) }
                }
                if mirror {
                    do {
                        try legacyExecute(legacyURL, "UPDATE jobs SET hash=? WHERE id=?", [digests.python, key], busyMs: busyBudget(deadline))
                        normalized.insert(key)
                    } catch { fputs("Хэш задания не обновлён в старом журнале: \(error)\n", stderr) }
                } else if jobs[key]?.hash == digests.primary { normalized.insert(key) }
            }
            guard let receipt = old.receipt else { throw PrintError.message(unknownOutcomeText) }
            return receipt
        }
        if inflight.contains(key) { throw PrintError.message(inProgressText) }
        inflight.insert(key)
        return nil
    }
}

private struct HTTPRequest {
    let method: String
    let path: String
    let headers: [String: String]
    let body: Data
}

private func readRequest(_ descriptor: Int32) throws -> HTTPRequest {
    var received = Data()
    let delimiter = Data("\r\n\r\n".utf8)
    var headerEnd: Int?
    var expectedSize: Int?
    while received.count <= 6_020_000 {
        var buffer = [UInt8](repeating: 0, count: 8192)
        let count = Darwin.recv(descriptor, &buffer, buffer.count, 0)
        guard count > 0 else { throw PrintError.message("Неполный HTTP-запрос") }
        received.append(contentsOf: buffer[0..<count])
        if headerEnd == nil, let range = received.range(of: delimiter) {
            headerEnd = range.upperBound
            guard range.lowerBound <= 16_384,
                  let headerText = String(data: received[..<range.lowerBound], encoding: .utf8) else {
                throw PrintError.message("Некорректные HTTP-заголовки")
            }
            var lines = headerText.components(separatedBy: "\r\n")
            guard let requestLine = lines.first else { throw PrintError.message("Некорректный HTTP-запрос") }
            lines.removeFirst()
            var headers: [String: String] = [:]
            for line in lines {
                guard let separator = line.firstIndex(of: ":") else { continue }
                headers[String(line[..<separator]).lowercased()] = line[line.index(after: separator)...]
                    .trimmingCharacters(in: .whitespaces)
            }
            let length = Int(headers["content-length"] ?? "0") ?? -1
            guard length >= 0, length <= 6_000_000 else { throw PrintError.message("Некорректный размер задания") }
            expectedSize = range.upperBound + length
            let parts = requestLine.split(separator: " ")
            guard parts.count == 3 else { throw PrintError.message("Некорректный HTTP-запрос") }
            if received.count >= expectedSize! {
                return HTTPRequest(
                    method: String(parts[0]), path: String(parts[1]), headers: headers,
                    body: received[range.upperBound..<expectedSize!]
                )
            }
        } else if let end = headerEnd, let size = expectedSize, received.count >= size {
            let headerText = String(data: received[..<(end - delimiter.count)], encoding: .utf8) ?? ""
            var lines = headerText.components(separatedBy: "\r\n")
            let parts = (lines.isEmpty ? "" : lines.removeFirst()).split(separator: " ")
            guard parts.count == 3 else { throw PrintError.message("Некорректный HTTP-запрос") }
            var headers: [String: String] = [:]
            for line in lines {
                guard let separator = line.firstIndex(of: ":") else { continue }
                headers[String(line[..<separator]).lowercased()] = line[line.index(after: separator)...]
                    .trimmingCharacters(in: .whitespaces)
            }
            return HTTPRequest(
                method: String(parts[0]), path: String(parts[1]), headers: headers,
                body: received[end..<size]
            )
        }
    }
    throw PrintError.message("HTTP-запрос слишком большой")
}

private func sendAll(_ descriptor: Int32, data: Data) {
    data.withUnsafeBytes { rawBuffer in
        guard var pointer = rawBuffer.baseAddress else { return }
        var remaining = data.count
        while remaining > 0 {
            let sent = Darwin.send(descriptor, pointer, remaining, 0)
            if sent <= 0 { return }
            remaining -= sent
            pointer = pointer.advanced(by: sent)
        }
    }
}

private func respond(_ descriptor: Int32, status: Int, value: [String: Any], origin: String?) {
    let body = (try? JSONSerialization.data(withJSONObject: value)) ?? Data("{}".utf8)
    let reason = [200: "OK", 403: "Forbidden", 404: "Not Found", 409: "Conflict", 503: "Service Unavailable"][status] ?? "Error"
    var headers = [
        "HTTP/1.1 \(status) \(reason)",
        "Content-Type: application/json; charset=utf-8",
        "Content-Length: \(body.count)",
        "Cache-Control: no-store",
        "Connection: close",
    ]
    if let origin, allowedOrigins.contains(origin) {
        headers += [
            "Access-Control-Allow-Origin: \(origin)",
            "Vary: Origin",
            "Access-Control-Allow-Methods: GET, POST, OPTIONS",
            "Access-Control-Allow-Headers: Content-Type, X-WMS-Print",
            "Access-Control-Allow-Private-Network: true",
        ]
    }
    sendAll(descriptor, data: Data((headers.joined(separator: "\r\n") + "\r\n\r\n").utf8) + body)
}

private func handle(_ descriptor: Int32, printer: Printer) {
    defer { Darwin.close(descriptor) }
    let deadline = Date().addingTimeInterval(requestBudget)
    var timeout = timeval(tv_sec: 15, tv_usec: 0)
    setsockopt(descriptor, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout.size(ofValue: timeout)))
    do {
        let request = try readRequest(descriptor)
        let origin = request.headers["origin"]
        let effectiveOrigin = origin ?? localOrigin
        let allowed = request.headers["host"] == "127.0.0.1:\(port)" && allowedOrigins.contains(effectiveOrigin)
        guard allowed else { respond(descriptor, status: 403, value: [:], origin: origin); return }
        if request.method == "OPTIONS" {
            respond(descriptor, status: 200, value: [:], origin: origin)
        } else if request.method == "GET" && request.path == "/health" {
            do {
                respond(descriptor, status: 200, value: ["app": appName, "build": buildID, "printer": try defaultPrinter()], origin: origin)
            } catch {
                respond(descriptor, status: 503, value: ["app": appName, "build": buildID, "error": String(describing: error)], origin: origin)
            }
        } else if request.method == "POST" && request.path == "/print" && request.headers["x-wms-print"] == "1" {
            do {
                guard let body = try JSONSerialization.jsonObject(with: request.body) as? [String: Any] else {
                    throw PrintError.message("Некорректное задание печати")
                }
                respond(descriptor, status: 200, value: ["receipt": try printer.printJob(body, deadline: deadline)], origin: origin)
            } catch {
                respond(descriptor, status: 409, value: ["error": String(describing: error)], origin: origin)
            }
        } else {
            respond(descriptor, status: request.method == "POST" ? 403 : 404, value: [:], origin: origin)
        }
    } catch {
        respond(descriptor, status: 409, value: ["error": String(describing: error)], origin: nil)
    }
}

private func testPNG(width: Int, height: Int, alpha: UInt8, hasAlphaChannel: Bool = true, dpi: Double? = nil) -> Data {
    let space = CGColorSpace(name: CGColorSpace.sRGB)!
    let info = hasAlphaChannel ? CGImageAlphaInfo.premultipliedLast : CGImageAlphaInfo.noneSkipLast
    let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                            space: space, bitmapInfo: info.rawValue)!
    context.clear(CGRect(x: 0, y: 0, width: width, height: height))
    if !hasAlphaChannel {
        context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    }
    if alpha > 0 {
        context.setFillColor(CGColor(red: 0, green: 0, blue: 0, alpha: CGFloat(alpha) / 255))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height / 2))
    }
    let output = NSMutableData()
    let destination = CGImageDestinationCreateWithData(output, "public.png" as CFString, 1, nil)!
    var properties: [CFString: Any] = [:]
    if let dpi { properties[kCGImagePropertyDPIWidth] = dpi; properties[kCGImagePropertyDPIHeight] = dpi }
    CGImageDestinationAddImage(destination, context.makeImage()!, properties as CFDictionary)
    CGImageDestinationFinalize(destination)
    return output as Data
}

private func firstPixel(_ png: Data, row: Int) -> [UInt8] {
    let source = CGImageSourceCreateWithData(png as CFData, nil)!
    let image = CGImageSourceCreateImageAtIndex(source, 0, nil)!
    var pixels = [UInt8](repeating: 0, count: image.width * image.height * 4)
    let context = CGContext(data: &pixels, width: image.width, height: image.height, bitsPerComponent: 8,
                            bytesPerRow: image.width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
    return Array(pixels[row * image.width * 4..<row * image.width * 4 + 4])
}

private func pngDPI(_ png: Data) -> Double? {
    let source = CGImageSourceCreateWithData(png as CFData, nil)!
    let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
    return (properties?[kCGImagePropertyDPIWidth] as? NSNumber)?.doubleValue
}

private func legacyRows(_ url: URL) -> [String: String] {
    var db: OpaquePointer?
    var statement: OpaquePointer?
    defer { sqlite3_finalize(statement); sqlite3_close(db) }
    guard sqlite3_open_v2(url.path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK,
          sqlite3_prepare_v2(db, "SELECT id, COALESCE(receipt, '-') FROM jobs", -1, &statement, nil) == SQLITE_OK else { return [:] }
    var rows: [String: String] = [:]
    while sqlite3_step(statement) == SQLITE_ROW {
        rows[String(cString: sqlite3_column_text(statement, 0))] = String(cString: sqlite3_column_text(statement, 1))
    }
    return rows
}

private func runSelfTest() throws {
    func fail(_ text: String) -> PrintError { PrintError.message("Самопроверка не пройдена: \(text)") }
    func refused(_ body: () throws -> String) -> String? {
        do { _ = try body(); return nil } catch { return String(describing: error) }
    }
    func says(_ body: () throws -> String, _ part: String) -> Bool { (refused(body) ?? "").lowercased().contains(part.lowercased()) }
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("wms-print-self-test-\(UUID().uuidString)")
    defer { try? FileManager.default.removeItem(at: directory) }
    var submissions = 0
    let printer = try Printer(
        directory: directory,
        submit: { _, _, _, _, mark in try mark(); submissions += 1; return "test-1" },
        queue: { _ in "test-printer" }
    )
    let opaque = testPNG(width: 4, height: 4, alpha: 255, hasAlphaChannel: false)
    func jobBody(_ key: String, _ png: Data) -> [String: Any] {
        ["idempotencyKey": key, "imageDataUrl": "data:image/png;base64," + png.base64EncodedString(),
         "widthMm": 58, "heightMm": 40]
    }
    let body = jobBody("self-test", opaque)
    guard try printer.printJob(body) == "test-1", try printer.printJob(body) == "test-1", submissions == 1 else {
        throw PrintError.message("Проверка защиты от повторной печати не пройдена")
    }
    guard parseReceipt("request id is Test_Printer-41 (1 file)", queue: "Test_Printer") == "Test_Printer-41",
          parseReceipt("id запроса Test_Printer-42 (файлов 1)", queue: "Test_Printer") == "Test_Printer-42" else {
        throw PrintError.message("Проверка квитанции очереди не пройдена")
    }
    guard FileManager.default.isExecutableFile(atPath: "/usr/bin/lp"),
          FileManager.default.isExecutableFile(atPath: "/usr/bin/lpstat") else {
        throw PrintError.message("Системная печать macOS недоступна")
    }
    // The label size reaches macOS exactly as in the installed release; the size is part of the identity.
    guard printArguments(queue: "Test_Printer", label: "/tmp/label.png", width: 58, height: 40)
            == ["-d", "Test_Printer", "-o", "media=Custom.58x40mm", "-o", "fit-to-page", "-o", "copies=1", "--", "/tmp/label.png"],
          millimeters(58.5) == "58.50" else { throw fail("lp arguments differ from the installed release") }
    guard try labelSize(["widthMm": 58, "heightMm": 40]).width == 58,
          (try? labelSize(["widthMm": 58])) == nil, (try? labelSize(["widthMm": 5, "heightMm": 40])) == nil else {
        throw fail("label size validation")
    }
    let sample = identityDigests(Data("abc".utf8), LabelSize(width: 58, height: 40))
    func sha(_ text: String) -> String { SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined() }
    guard sample.primary == sha("abc|58.0x40.0"), sample.python == sha("abc|580x400"), sample.legacy == sha("abc") else {
        throw fail("identity formula differs from the installed releases")
    }

    var wrongSize = body
    wrongSize["widthMm"] = 60
    guard says({ try printer.printJob(wrongSize) }, "изменилось"), submissions == 1 else { throw fail("same key, other size") }

    // A failure before the OS boundary, or a failed journal write, leaves the key retryable.
    var attempt = 0
    let retry = try Printer(
        directory: directory.appendingPathComponent("retry"),
        submit: { _, _, _, _, mark in
            attempt += 1
            try mark()
            if attempt == 1 { throw PrintError.notSent("lp did not start") }
            return "retry-\(attempt)"
        },
        queue: { _ in "test-printer" }
    )
    guard refused({ try retry.printJob(jobBody("k1", opaque)) }) != nil else { throw fail("proven failure was not reported") }
    guard try retry.printJob(jobBody("k1", opaque)) == "retry-2" else { throw fail("retry after notSent") }
    let broken = Data(pngPrefix) + Data("x".utf8)
    guard refused({ try retry.printJob(jobBody("broken", broken)) }) != nil, attempt == 2,
          refused({ try retry.printJob(jobBody("broken", broken)) }) != nil, attempt == 2 else {
        throw fail("undecodable PNG reached the printer")
    }
    // Memory rollback when the first journal write fails.
    var sent = 0
    let writes = try Printer(
        directory: directory.appendingPathComponent("writes"),
        submit: { _, _, _, _, mark in try mark(); sent += 1; return "w-\(sent)" }, queue: { _ in "test-printer" })
    let store = directory.appendingPathComponent("writes/direct-jobs.json")
    try? FileManager.default.removeItem(at: store)
    try FileManager.default.createDirectory(at: store, withIntermediateDirectories: false)
    if refused({ try writes.printJob(jobBody("w1", opaque)) }) == nil || sent != 0 { throw fail("write failure") }
    try FileManager.default.removeItem(at: store)
    guard try writes.printJob(jobBody("w1", opaque)) == "w-1", sent == 1 else { throw fail("rollback of memory state") }

    // The journal of the previous Python release keeps protecting its keys and is kept up to date.
    let legacyDirectory = directory.appendingPathComponent("legacy")
    try FileManager.default.createDirectory(at: legacyDirectory, withIntermediateDirectories: true)
    let legacyFile = legacyDirectory.appendingPathComponent("direct-jobs.sqlite3")
    var database: OpaquePointer?
    let hash = SHA256.hash(data: opaque).map { String(format: "%02x", $0) }.joined()
    guard sqlite3_open(legacyFile.path, &database) == SQLITE_OK,
          sqlite3_exec(database, "CREATE TABLE jobs (id TEXT PRIMARY KEY, hash TEXT, receipt TEXT);"
                       + "INSERT INTO jobs VALUES ('old-key', '\(hash)', 'Old-5');"
                       + "INSERT INTO jobs VALUES ('old-open', '\(hash)', NULL);", nil, nil, nil) == SQLITE_OK else {
        throw fail("legacy fixture")
    }
    sqlite3_close(database)
    legacyBusyMs = 100
    var legacySent = 0
    var legacyFail = false
    let migrated = try Printer(directory: legacyDirectory, submit: { _, _, _, _, mark in
        try mark(); legacySent += 1
        if legacyFail { throw PrintError.notSent("no lp") }
        return "new-\(legacySent)"
    }, queue: { _ in "test-printer" })
    guard try migrated.printJob(jobBody("old-key", opaque)) == "Old-5", legacySent == 0,
          says({ try migrated.printJob(jobBody("old-open", opaque)) }, "проверьте принтер"),
          legacySent == 0,
          try Printer(directory: legacyDirectory, submit: { _, _, _, _, _ in "x" }, queue: { _ in "q" })
              .printJob(jobBody("old-key", opaque)) == "Old-5" else { throw fail("legacy import") }
    // New marks and receipts are written into the old journal too (a way back to the Python build).
    guard try migrated.printJob(jobBody("fresh", opaque)) == "new-1",
          legacyRows(legacyFile)["fresh"] == "new-1" else { throw fail("legacy mirror receipt") }
    legacyFail = true
    guard refused({ try migrated.printJob(jobBody("lost", opaque)) }) != nil, legacyRows(legacyFile)["lost"] == nil else {
        throw fail("legacy mirror rollback")
    }

    // A locked old journal: nothing is printed until it can be read; then the history is used.
    let busyDirectory = directory.appendingPathComponent("busy")
    try FileManager.default.createDirectory(at: busyDirectory, withIntermediateDirectories: true)
    let busyFile = busyDirectory.appendingPathComponent("direct-jobs.sqlite3")
    try FileManager.default.copyItem(at: legacyFile, to: busyFile)
    var holder: OpaquePointer?
    guard sqlite3_open(busyFile.path, &holder) == SQLITE_OK,
          sqlite3_exec(holder, "BEGIN EXCLUSIVE", nil, nil, nil) == SQLITE_OK else { throw fail("busy fixture") }
    var busySent = 0
    let blocked = try Printer(directory: busyDirectory, submit: { _, _, _, _, mark in try mark(); busySent += 1; return "b-1" },
                              queue: { _ in "test-printer" })
    guard says({ try blocked.printJob(jobBody("old-key", opaque)) }, "Закройте старую версию"),
          says({ try blocked.printJob(jobBody("brand-new", opaque)) }, "Закройте старую версию"),
          busySent == 0 else { throw fail("locked journal must stop printing") }
    sqlite3_exec(holder, "COMMIT", nil, nil, nil)
    sqlite3_close(holder)
    guard try blocked.printJob(jobBody("old-key", opaque)) == "Old-5", busySent == 0,
          try blocked.printJob(jobBody("brand-new", opaque)) == "b-1" else { throw fail("import after the lock was released") }

    // A damaged old journal is a warning only: the warehouse keeps working.
    let damagedDirectory = directory.appendingPathComponent("damaged")
    try FileManager.default.createDirectory(at: damagedDirectory, withIntermediateDirectories: true)
    try Data("this is not sqlite at all, only text".utf8).write(to: damagedDirectory.appendingPathComponent("direct-jobs.sqlite3"))
    let damaged = try Printer(directory: damagedDirectory, submit: { _, _, _, _, mark in try mark(); return "d-1" },
                              queue: { _ in "test-printer" })
    guard try damaged.printJob(jobBody("any", opaque)) == "d-1" else { throw fail("damaged old journal stopped printing") }

    // One deadline: waiting for the queue ends in time and is reported as "not sent";
    // the key's own history is answered at once; too little time left never starts a job.
    let slowDirectory = directory.appendingPathComponent("slow")
    var slowSent = 0
    let slow = try Printer(directory: slowDirectory, submit: { _, _, _, _, mark in
        try mark(); slowSent += 1; Thread.sleep(forTimeInterval: 1.5); return "s-\(slowSent)"
    }, queue: { _ in "test-printer" })
    let worker = Thread { _ = try? slow.printJob(jobBody("inflight", opaque)) }
    worker.start()
    Thread.sleep(forTimeInterval: 0.4)
    let started = Date()
    guard says({ try slow.printJob(jobBody("inflight", opaque)) }, "проверьте принтер"),
          Date().timeIntervalSince(started) < 1 else { throw fail("a known key waited for the print queue") }
    Thread.sleep(forTimeInterval: 1.5)
    guard says({ try slow.printJob(jobBody("late", opaque), deadline: Date().addingTimeInterval(3)) }, "не отправлялось"),
          slowSent == 1 else { throw fail("deadline: a late job was started") }

    // A clean install creates the old journal and keeps it level, so going back to the Python build is safe.
    let cleanDirectory = directory.appendingPathComponent("clean")
    let clean = try Printer(directory: cleanDirectory, submit: { _, _, _, _, mark in try mark(); return "c-1" }, queue: { _ in "test-printer" })
    let cleanFile = cleanDirectory.appendingPathComponent("direct-jobs.sqlite3")
    guard FileManager.default.fileExists(atPath: cleanFile.path), try clean.printJob(jobBody("c", opaque)) == "c-1",
          legacyRows(cleanFile)["c"] == "c-1" else { throw fail("old journal on a clean install") }
    // Keys known only to the json are copied into the old journal when the program starts.
    let levelDirectory = directory.appendingPathComponent("level")
    try FileManager.default.createDirectory(at: levelDirectory, withIntermediateDirectories: true)
    let levelHash = SHA256.hash(data: opaque).map { String(format: "%02x", $0) }.joined()
    try JSONEncoder().encode(["json-only": StoredJob(hash: levelHash, receipt: "J-9"),
                              "json-open": StoredJob(hash: levelHash, receipt: nil)])
        .write(to: levelDirectory.appendingPathComponent("direct-jobs.json"))
    var level: OpaquePointer?
    guard sqlite3_open(levelDirectory.appendingPathComponent("direct-jobs.sqlite3").path, &level) == SQLITE_OK,
          sqlite3_exec(level, legacySchema + ";INSERT INTO jobs VALUES ('json-open', '\(levelHash)', NULL)", nil, nil, nil) == SQLITE_OK
    else { throw fail("level fixture") }
    sqlite3_close(level)
    _ = try Printer(directory: levelDirectory, submit: { _, _, _, _, _ in "x" }, queue: { _ in "q" })
    guard legacyRows(levelDirectory.appendingPathComponent("direct-jobs.sqlite3"))["json-only"] == "J-9",
          legacyRows(levelDirectory.appendingPathComponent("direct-jobs.sqlite3"))["json-open"] == "-" else {
        throw fail("json keys were not copied into the old journal")
    }

    // A parallel repeat of a key that is being processed hears "in progress", never "not sent".
    let racingDirectory = directory.appendingPathComponent("racing")
    var racingSent = 0
    let racing = try Printer(directory: racingDirectory, submit: { _, _, _, _, mark in
        Thread.sleep(forTimeInterval: 1.0)  // still preparing: nothing is marked yet
        try mark(); racingSent += 1; return "r-1"
    }, queue: { _ in "test-printer" })
    let first = Thread { _ = try? racing.printJob(jobBody("race", opaque)) }
    first.start()
    Thread.sleep(forTimeInterval: 0.3)
    let twin = refused({ try racing.printJob(jobBody("race", opaque), deadline: Date().addingTimeInterval(7)) }) ?? ""
    guard twin.contains("в работе"), !twin.contains("не отправлялось") else { throw fail("parallel repeat: \(twin)") }
    Thread.sleep(forTimeInterval: 1.2)
    guard try racing.printJob(jobBody("race", opaque)) == "r-1", racingSent == 1 else { throw fail("race result") }

    // Waiting for the journal may use up the budget: the job is then not sent and the mark is removed.
    let lateDirectory = directory.appendingPathComponent("late")
    var lateSent = 0
    let late = try Printer(directory: lateDirectory, submit: { _, _, _, _, mark in try mark(); lateSent += 1; return "l-1" },
                           queue: { _ in "test-printer" })
    let lateFile = lateDirectory.appendingPathComponent("direct-jobs.sqlite3")
    var blocker: OpaquePointer?
    guard sqlite3_open(lateFile.path, &blocker) == SQLITE_OK, sqlite3_exec(blocker, "BEGIN EXCLUSIVE", nil, nil, nil) == SQLITE_OK
    else { throw fail("late fixture") }
    legacyBusyMs = 3000
    Thread.detachNewThread { Thread.sleep(forTimeInterval: 1.2); sqlite3_exec(blocker, "COMMIT", nil, nil, nil) }
    let tight = Date().addingTimeInterval(minimumToStart + 0.6)
    let lateText = refused({ try late.printJob(jobBody("late-key", opaque), deadline: tight) }) ?? ""
    sqlite3_close(blocker)
    legacyBusyMs = 100
    guard lateText.contains("не отправлялось"), lateSent == 0, legacyRows(lateFile)["late-key"] == nil,
          try late.printJob(jobBody("late-key", opaque)) == "l-1", lateSent == 1 else { throw fail("budget spent on the journal: \(lateText)") }

    // Rows written by the Python release (its identity formula) are recognised, and the
    // rows this program writes are readable by it: the same key is never printed twice.
    let pyDirectory = directory.appendingPathComponent("pyformat")
    try FileManager.default.createDirectory(at: pyDirectory, withIntermediateDirectories: true)
    let pyFile = pyDirectory.appendingPathComponent("direct-jobs.sqlite3")
    let pyDigest = identityDigests(opaque, LabelSize(width: 58, height: 40)).python
    var pyDB: OpaquePointer?
    guard sqlite3_open(pyFile.path, &pyDB) == SQLITE_OK,
          sqlite3_exec(pyDB, legacySchema + ";INSERT INTO jobs VALUES ('py-key', '\(pyDigest)', 'Py-1')", nil, nil, nil) == SQLITE_OK
    else { throw fail("python-format fixture") }
    sqlite3_close(pyDB)
    var pySent = 0
    let pyPrinter = try Printer(directory: pyDirectory, submit: { _, _, _, _, mark in try mark(); pySent += 1; return "py-new" },
                                queue: { _ in "test-printer" })
    guard try pyPrinter.printJob(jobBody("py-key", opaque)) == "Py-1", pySent == 0,
          try pyPrinter.printJob(jobBody("swift-key", opaque)) == "py-new" else { throw fail("python-format identity") }
    var check: OpaquePointer?
    var query: OpaquePointer?
    guard sqlite3_open_v2(pyFile.path, &check, SQLITE_OPEN_READONLY, nil) == SQLITE_OK,
          sqlite3_prepare_v2(check, "SELECT hash FROM jobs WHERE id='swift-key'", -1, &query, nil) == SQLITE_OK,
          sqlite3_step(query) == SQLITE_ROW, String(cString: sqlite3_column_text(query, 0)) == pyDigest else {
        throw fail("mirror row is not in the Python identity format")
    }
    sqlite3_finalize(query)
    sqlite3_close(check)

    // A confirmed repeat rewrites the hash of imported records in the form each reader expects.
    let normDirectory = directory.appendingPathComponent("normalize")
    try FileManager.default.createDirectory(at: normDirectory, withIntermediateDirectories: true)
    let normForms = identityDigests(opaque, LabelSize(width: 58, height: 40))
    try JSONEncoder().encode(["mac-key": StoredJob(hash: normForms.primary, receipt: "Mac-1")])
        .write(to: normDirectory.appendingPathComponent("direct-jobs.json"))
    var normDB: OpaquePointer?
    guard sqlite3_open(normDirectory.appendingPathComponent("direct-jobs.sqlite3").path, &normDB) == SQLITE_OK,
          sqlite3_exec(normDB, legacySchema + ";INSERT INTO jobs VALUES ('py-key', '\(normForms.python)', 'Py-2')", nil, nil, nil) == SQLITE_OK
    else { throw fail("normalize fixture") }
    sqlite3_close(normDB)
    let normPrinter = try Printer(directory: normDirectory, submit: { _, _, _, _, _ in "never" }, queue: { _ in "q" })
    func storedHash(_ file: URL, _ key: String) -> String? {
        var db: OpaquePointer?
        var query: OpaquePointer?
        defer { sqlite3_finalize(query); sqlite3_close(db) }
        guard sqlite3_open_v2(file.path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK,
              sqlite3_prepare_v2(db, "SELECT hash FROM jobs WHERE id='\(key)'", -1, &query, nil) == SQLITE_OK,
              sqlite3_step(query) == SQLITE_ROW else { return nil }
        return String(cString: sqlite3_column_text(query, 0))
    }
    let normFile = normDirectory.appendingPathComponent("direct-jobs.sqlite3")
    guard try normPrinter.printJob(jobBody("mac-key", opaque)) == "Mac-1", try normPrinter.printJob(jobBody("py-key", opaque)) == "Py-2",
          storedHash(normFile, "mac-key") == normForms.python,   // the Python release reads this
          storedHash(normFile, "py-key") == normForms.python,
          let json = try? JSONDecoder().decode([String: StoredJob].self, from: Data(contentsOf: normDirectory.appendingPathComponent("direct-jobs.json"))),
          json["py-key"]?.hash == normForms.primary, json["mac-key"]?.hash == normForms.primary   // the previous Swift reads this
    else { throw fail("hash normalisation for the previous versions") }

    // A proven-unsent mark that cannot be removed now (journal locked) still frees the key,
    // in the same run and after a restart; a really unknown outcome stays blocked.
    let freeDirectory = directory.appendingPathComponent("free")
    var freeAttempt = 0
    var freeBlocker: OpaquePointer?
    let freeFile = freeDirectory.appendingPathComponent("direct-jobs.sqlite3")
    legacyBusyMs = 100
    let freePrinter = try Printer(directory: freeDirectory, submit: { _, _, _, _, mark in
        freeAttempt += 1
        try mark()
        if freeAttempt == 1 {
            guard sqlite3_open(freeFile.path, &freeBlocker) == SQLITE_OK,
                  sqlite3_exec(freeBlocker, "BEGIN EXCLUSIVE", nil, nil, nil) == SQLITE_OK else { throw fail("free fixture") }
            throw PrintError.notSent("lp did not start")   // the cleanup now meets a locked journal
        }
        return "free-\(freeAttempt)"
    }, queue: { _ in "test-printer" })
    guard refused({ try freePrinter.printJob(jobBody("fk", opaque)) }) != nil else { throw fail("free: first attempt") }
    sqlite3_exec(freeBlocker, "COMMIT", nil, nil, nil)
    sqlite3_close(freeBlocker)
    guard legacyRows(freeFile)["fk"] == "-" else { throw fail("free: the stale mark should still be in the journal") }
    guard try freePrinter.printJob(jobBody("fk", opaque)) == "free-2" else { throw fail("free: repeat in the same run") }
    // restart: the stale mark must not come back from the old journal
    var restartAttempt = 0
    var restartBlocker: OpaquePointer?
    let restartDirectory = directory.appendingPathComponent("restart")
    let restartFile = restartDirectory.appendingPathComponent("direct-jobs.sqlite3")
    let beforeRestart = try Printer(directory: restartDirectory, submit: { _, _, _, _, mark in
        try mark()
        guard sqlite3_open(restartFile.path, &restartBlocker) == SQLITE_OK,
              sqlite3_exec(restartBlocker, "BEGIN EXCLUSIVE", nil, nil, nil) == SQLITE_OK else { throw fail("restart fixture") }
        throw PrintError.notSent("lp did not start")
    }, queue: { _ in "test-printer" })
    _ = refused({ try beforeRestart.printJob(jobBody("rk", opaque)) })
    sqlite3_exec(restartBlocker, "COMMIT", nil, nil, nil)
    sqlite3_close(restartBlocker)
    let second = try Printer(directory: restartDirectory, submit: { _, _, _, _, mark in try mark(); restartAttempt += 1; return "restart-1" },
                             queue: { _ in "test-printer" })
    guard try second.printJob(jobBody("rk", opaque)) == "restart-1", restartAttempt == 1 else { throw fail("free: repeat after a restart") }
    let unknown = try Printer(directory: directory.appendingPathComponent("unknown"), submit: { _, _, _, _, mark in
        try mark(); throw PrintError.message("lp outcome unknown") }, queue: { _ in "test-printer" })
    _ = refused({ try unknown.printJob(jobBody("uk", opaque)) })
    let unknownAgain = try Printer(directory: directory.appendingPathComponent("unknown"), submit: { _, _, _, _, _ in "never" }, queue: { _ in "q" })
    guard says({ try unknownAgain.printJob(jobBody("uk", opaque)) }, "проверьте принтер") else { throw fail("an unknown outcome must stay blocked") }
    legacyBusyMs = 100

    // A tool that ignores SIGTERM is killed; the output pipe is drained meanwhile.
    let hung = Date()
    let stuck = try run("/bin/sh", ["-c", "trap '' TERM; exec sleep 30"], timeout: 0.3, grace: 0.3)
    guard stuck.timedOut, Date().timeIntervalSince(hung) < 5 else { throw fail("hung process was not stopped") }
    let big = try run("/usr/bin/head", ["-c", "400000", "/dev/zero"], timeout: 10)
    guard !big.timedOut, big.status == 0, big.output.utf8.count == 400_000 else { throw fail("pipe draining") }
    do { _ = try run("/nonexistent/lp", [], timeout: 1); throw fail("launch error") } catch PrintError.notSent { }

    // PNG checks: damaged data is refused, transparency is painted on white, resolution is kept.
    guard (try? preparePNG(Data(opaque.prefix(opaque.count - 20)))) == nil,
          (try? preparePNG(Data(opaque.prefix(opaque.count / 2)))) == nil,
          (try? preparePNG(Data(pngPrefix))) == nil else { throw fail("damaged PNG accepted") }
    guard try preparePNG(opaque) == opaque else { throw fail("opaque PNG was changed") }
    let glass = try preparePNG(testPNG(width: 4, height: 4, alpha: 0))
    let half = try preparePNG(testPNG(width: 4, height: 4, alpha: 255))
    guard firstPixel(glass, row: 0) == [255, 255, 255, 255], firstPixel(half, row: 0) == [0, 0, 0, 255] ||
          firstPixel(half, row: 3) == [0, 0, 0, 255] else { throw fail("transparent background") }
    let sharp = try preparePNG(testPNG(width: 464, height: 320, alpha: 255, dpi: 203))
    guard let dpi = pngDPI(sharp), abs(dpi - 203) < 0.5, firstPixel(sharp, row: 0).prefix(3) != [128, 128, 128] else {
        throw fail("resolution of the label was lost")
    }
    print("WMS Print Direct macOS: package OK")
}

/// Asks whatever listens on the port who it is: build id and /health status when it is WMS Print, otherwise nil.
private func liveInstance(attempts: Int) -> (build: String, healthy: Bool)? {
    for attempt in 0..<attempts {
        let descriptor = socket(AF_INET, SOCK_STREAM, 0)
        if descriptor >= 0 {
            defer { Darwin.close(descriptor) }
            var timeout = timeval(tv_sec: 3, tv_usec: 0)
            setsockopt(descriptor, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout.size(ofValue: timeout)))
            setsockopt(descriptor, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout.size(ofValue: timeout)))
            var address = sockaddr_in(
                sin_len: UInt8(MemoryLayout<sockaddr_in>.size), sin_family: sa_family_t(AF_INET),
                sin_port: port.bigEndian, sin_addr: in_addr(s_addr: inet_addr("127.0.0.1")),
                sin_zero: (0, 0, 0, 0, 0, 0, 0, 0)
            )
            let connected = withUnsafePointer(to: &address) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    Darwin.connect(descriptor, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
            if connected == 0 {
                let request = "GET /health HTTP/1.1\r\nHost: 127.0.0.1:\(port)\r\nConnection: close\r\n\r\n"
                sendAll(descriptor, data: Data(request.utf8))
                var received = Data()
                var buffer = [UInt8](repeating: 0, count: 4096)
                while received.count < 65_536 {
                    let count = Darwin.recv(descriptor, &buffer, buffer.count, 0)
                    if count <= 0 { break }
                    received.append(contentsOf: buffer[0..<count])
                }
                if let split = received.range(of: Data("\r\n\r\n".utf8)),
                   let value = try? JSONSerialization.jsonObject(with: received[split.upperBound...]) as? [String: Any],
                   value["app"] as? String == appName {
                    let status = String(data: received[..<split.lowerBound], encoding: .utf8) ?? ""
                    return (value["build"] as? String ?? "", status.hasPrefix("HTTP/1.1 200"))
                }
            }
        }
        if attempt + 1 < attempts { Thread.sleep(forTimeInterval: 0.3) }
    }
    return nil
}

/// True when the running copy is this very build (quiet exit); throws for another build.
private func existingCopyIsCurrent(attempts: Int) throws -> Bool {
    guard let running = liveInstance(attempts: attempts) else { return false }
    guard running.build == buildID else {
        throw PrintError.message("Запущена другая версия WMS Print. Закройте её и откройте эту снова.")
    }
    // A /health error (no printer, driver trouble) is not "working".
    guard running.healthy else {
        throw PrintError.message("Эта версия WMS Print уже запущена, но проверка принтера (/health) не проходит. Проверьте принтер или закройте программу и откройте её снова.")
    }
    print("WMS Print уже запущена и работает. Это окно можно закрыть.")
    return true
}

private var instanceLock: Int32 = -1  // held until the process ends; the OS drops it on a crash too

private func runServer() throws {
    signal(SIGPIPE, SIG_IGN)
    // WMS_PRINT_STATE_DIR exists for tests, so they never touch the operator's journal.
    let directory: URL
    if let override = ProcessInfo.processInfo.environment["WMS_PRINT_STATE_DIR"], !override.isEmpty {
        directory = URL(fileURLWithPath: override)
    } else {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        directory = appSupport.appendingPathComponent("WMS Print/direct")
    }
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    instanceLock = open(directory.appendingPathComponent("instance.lock").path, O_CREAT | O_RDWR, 0o600)
    if instanceLock >= 0, flock(instanceLock, LOCK_EX | LOCK_NB) != 0 {
        // Opened twice: the first copy is working, so stay quiet and succeed (same build only).
        if try existingCopyIsCurrent(attempts: 10) { return }
        throw PrintError.message("WMS Print уже открыта, но не отвечает. Закройте её окно и откройте программу снова.")
    }
    let descriptor = socket(AF_INET, SOCK_STREAM, 0)
    guard descriptor >= 0 else { throw PrintError.message("Не удалось открыть локальный порт") }
    var reuse: Int32 = 1
    setsockopt(descriptor, SOL_SOCKET, SO_REUSEADDR, &reuse, socklen_t(MemoryLayout.size(ofValue: reuse)))
    var address = sockaddr_in(
        sin_len: UInt8(MemoryLayout<sockaddr_in>.size), sin_family: sa_family_t(AF_INET),
        sin_port: port.bigEndian, sin_addr: in_addr(s_addr: inet_addr("127.0.0.1")),
        sin_zero: (0, 0, 0, 0, 0, 0, 0, 0)
    )
    let bound = withUnsafePointer(to: &address) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            Darwin.bind(descriptor, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    guard bound == 0, Darwin.listen(descriptor, 128) == 0 else {
        Darwin.close(descriptor)
        if try existingCopyIsCurrent(attempts: 3) { return }  // an older copy without a lock file is another build
        throw PrintError.message("Порт \(port) занят другой программой. WMS Print её не закрывает: закройте эту программу или перезагрузите компьютер.")
    }
    let printer = try Printer(directory: directory)
    print("WMS Print запущена. Сканируйте в WMS. Оставьте это окно открытым.")
    fflush(stdout)
    while true {
        let client = Darwin.accept(descriptor, nil, nil)
        if client >= 0 { DispatchQueue.global(qos: .userInitiated).async { handle(client, printer: printer) } }
    }
}

do {
    if CommandLine.arguments.contains("--self-test") { try runSelfTest() } else { try runServer() }
} catch {
    fputs("\(String(describing: error))\n", stderr)
    exit(1)
}
