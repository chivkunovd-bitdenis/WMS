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

private func defaultPrinter() throws -> String {
    let result = try run("/usr/bin/lpstat", ["-d"], timeout: 10)
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

/// Exact queue media for the label size, e.g. "58x40mm" or "58x40mm.Borderless".
/// No exact match means no media option: the queue keeps its own default.
private func matchMedia(_ listing: String, width: Double, height: Double) -> String? {
    guard let expression = try? NSRegularExpression(
        pattern: "^([0-9]+(?:\\.[0-9]+)?)x([0-9]+(?:\\.[0-9]+)?)mm(\\.Borderless)?$") else { return nil }
    var plain: String?
    var borderless: String?
    for line in listing.components(separatedBy: .newlines) where line.hasPrefix("PageSize/") || line.hasPrefix("PageSize:") {
        guard let colon = line.firstIndex(of: ":") else { continue }
        for raw in line[line.index(after: colon)...].split(whereSeparator: { $0 == " " || $0 == "\t" }) {
            let name = raw.hasPrefix("*") ? String(raw.dropFirst()) : String(raw)
            guard let match = expression.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)),
                  let w = Range(match.range(at: 1), in: name).flatMap({ Double(name[$0]) }),
                  let h = Range(match.range(at: 2), in: name).flatMap({ Double(name[$0]) }),
                  abs(w - width) < 0.05, abs(h - height) < 0.05 else { continue }
            if match.range(at: 3).location == NSNotFound { plain = plain ?? name } else { borderless = borderless ?? name }
        }
    }
    return plain ?? borderless
}

private func queueMedia(_ queue: String, size: (Double, Double)?) -> String? {
    guard let size, let result = try? run("/usr/bin/lpoptions", ["-p", queue, "-l"], timeout: 5),
          !result.timedOut, result.status == 0 else { return nil }
    return matchMedia(result.output, width: size.0, height: size.1)
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
    context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    context.fill(rect)
    context.draw(image, in: rect)
    let output = NSMutableData()
    guard let flat = context.makeImage(),
          let destination = CGImageDestinationCreateWithData(output, "public.png" as CFString, 1, nil) else { throw invalid }
    CGImageDestinationAddImage(destination, flat, nil)
    guard CGImageDestinationFinalize(destination) else { throw invalid }
    return output as Data
}

private func submitToDefaultPrinter(_ data: Data, queue: String, size: (Double, Double)?,
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
    var arguments = ["-d", queue, "-o", "fit-to-page", "-o", "copies=1"]
    if let media = queueMedia(queue, size: size) { arguments += ["-o", "media=\(media)", "-o", "number-up=1"] }
    arguments += ["--", label.path]
    try mark()  // the next step is the first one that can reach the OS queue
    let result = try run("/usr/bin/lp", arguments, timeout: lpTimeout)
    guard !result.timedOut, result.status == 0 else {
        throw PrintError.message("Исход печати неизвестен. Проверьте очередь принтера.")
    }
    // CUPS localizes the surrounding text even with LC_ALL=C (for example,
    // "id запроса queue-123").  The queue receipt itself has a stable form.
    guard let receipt = parseReceipt(result.output, queue: queue) else {
        throw PrintError.message("macOS не подтвердила приём задания. Проверьте очередь принтера.")
    }
    return receipt
}

/// Jobs of the previous (Python) release lived in direct-jobs.sqlite3.
private func legacyJobs(at url: URL) -> [String: StoredJob] {
    var db: OpaquePointer?
    guard sqlite3_open_v2(url.path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else {
        sqlite3_close(db)
        fputs("Старый журнал \(url.lastPathComponent) не открыт; импорт пропущен\n", stderr)
        return [:]
    }
    defer { sqlite3_close(db) }
    var statement: OpaquePointer?
    guard sqlite3_prepare_v2(db, "SELECT id, hash, receipt FROM jobs", -1, &statement, nil) == SQLITE_OK else {
        fputs("Старый журнал \(url.lastPathComponent) не прочитан; импорт пропущен\n", stderr)
        return [:]
    }
    defer { sqlite3_finalize(statement) }
    var result: [String: StoredJob] = [:]
    while sqlite3_step(statement) == SQLITE_ROW {
        guard let id = sqlite3_column_text(statement, 0), let hash = sqlite3_column_text(statement, 1) else { continue }
        let receipt = sqlite3_column_text(statement, 2).map { String(cString: $0) }
        result[String(cString: id)] = StoredJob(hash: String(cString: hash), receipt: receipt)
    }
    return result
}

private final class Printer {
    private let lock = NSLock()
    private let storeURL: URL
    private let submit: (Data, String, (Double, Double)?, () throws -> Void) throws -> String
    private let queue: () throws -> String
    private var jobs: [String: StoredJob]

    init(
        directory: URL,
        submit: @escaping (Data, String, (Double, Double)?, () throws -> Void) throws -> String = submitToDefaultPrinter,
        queue: @escaping () throws -> String = defaultPrinter
    ) throws {
        self.submit = submit
        self.queue = queue
        self.storeURL = directory.appendingPathComponent("direct-jobs.json")
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
        // Keys written by the earlier Python release must still protect against repeats.
        let legacy = directory.appendingPathComponent("direct-jobs.sqlite3")
        if FileManager.default.fileExists(atPath: legacy.path) {
            var added = false
            for (key, job) in legacyJobs(at: legacy) where jobs[key] == nil {
                jobs[key] = job
                added = true
            }
            if added {
                do { try persist() } catch { fputs("Журнал после импорта не сохранён: \(error)\n", stderr) }
            }
        }
    }

    private func persist() throws {
        try JSONEncoder().encode(jobs).write(to: storeURL, options: .atomic)
    }

    func printJob(_ body: [String: Any]) throws -> String {
        guard let key = body["idempotencyKey"] as? String, (1...200).contains(key.count),
              let image = body["imageDataUrl"] as? String else {
            throw PrintError.message("Некорректное задание печати")
        }
        let prefix = "data:image/png;base64,"
        guard image.hasPrefix(prefix), let data = Data(base64Encoded: String(image.dropFirst(prefix.count))),
              data.count <= 4_000_000, data.starts(with: pngPrefix) else {
            throw PrintError.message("Ожидается корректная PNG-этикетка")
        }
        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        var size: (Double, Double)?
        if let width = (body["widthMm"] as? NSNumber)?.doubleValue, let height = (body["heightMm"] as? NSNumber)?.doubleValue,
           (1...1000).contains(width), (1...1000).contains(height) {
            size = (width, height)
        }

        lock.lock()
        defer { lock.unlock() }
        if let old = jobs[key] {
            guard old.hash == digest else { throw PrintError.message("Содержимое этого задания изменилось") }
            guard let receipt = old.receipt else {
                throw PrintError.message("Задание уже передавалось. Проверьте очередь принтера; повтор автоматически не отправлен.")
            }
            return receipt
        }

        // Anything below that fails before mark() leaves no trace: the key can be retried.
        let ready = try preparePNG(data)
        let queue = try queue()
        var marked = false
        let mark = { [self] in
            jobs[key] = StoredJob(hash: digest, receipt: nil)
            do { try persist() } catch {
                jobs[key] = nil  // not written, not sent: roll the memory back too
                throw PrintError.notSent("Не удалось записать журнал печати; задание не отправлялось")
            }
            marked = true
        }
        let receipt: String
        do {
            receipt = try submit(ready, queue, size, mark)
        } catch PrintError.notSent(let reason) {
            if marked {
                jobs[key] = nil
                try? persist()
            }
            throw PrintError.message(reason)
        }
        jobs[key] = StoredJob(hash: digest, receipt: receipt)
        // The job is already in the OS queue; a failed write must not report it as lost.
        do { try persist() } catch { fputs("Квитанция не записана в журнал: \(error)\n", stderr) }
        return receipt
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
                respond(descriptor, status: 200, value: ["app": appName, "printer": try defaultPrinter()], origin: origin)
            } catch {
                respond(descriptor, status: 503, value: ["app": appName, "error": String(describing: error)], origin: origin)
            }
        } else if request.method == "POST" && request.path == "/print" && request.headers["x-wms-print"] == "1" {
            do {
                guard let body = try JSONSerialization.jsonObject(with: request.body) as? [String: Any] else {
                    throw PrintError.message("Некорректное задание печати")
                }
                respond(descriptor, status: 200, value: ["receipt": try printer.printJob(body)], origin: origin)
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

private func testPNG(width: Int, height: Int, alpha: UInt8, hasAlphaChannel: Bool = true) -> Data {
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
    CGImageDestinationAddImage(destination, context.makeImage()!, nil)
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

private func runSelfTest() throws {
    func fail(_ text: String) -> PrintError { PrintError.message("Самопроверка не пройдена: \(text)") }
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("wms-print-self-test-\(UUID().uuidString)")
    defer { try? FileManager.default.removeItem(at: directory) }
    var submissions = 0
    let printer = try Printer(
        directory: directory,
        submit: { _, _, _, mark in try mark(); submissions += 1; return "test-1" },
        queue: { "test-printer" }
    )
    let opaque = testPNG(width: 4, height: 4, alpha: 255, hasAlphaChannel: false)
    let image = "data:image/png;base64," + opaque.base64EncodedString()
    let body: [String: Any] = ["idempotencyKey": "self-test", "imageDataUrl": image]
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

    // A failure before the OS boundary, or a failed journal write, leaves the key retryable.
    func jobBody(_ key: String, _ png: Data) -> [String: Any] {
        ["idempotencyKey": key, "imageDataUrl": "data:image/png;base64," + png.base64EncodedString()]
    }
    var attempt = 0
    let retry = try Printer(
        directory: directory.appendingPathComponent("retry"),
        submit: { _, _, _, mark in
            attempt += 1
            try mark()
            if attempt == 1 { throw PrintError.notSent("lp did not start") }
            return "retry-\(attempt)"
        },
        queue: { "test-printer" }
    )
    var refused = false
    do { _ = try retry.printJob(jobBody("k1", opaque)) } catch PrintError.message { refused = true }
    guard refused else { throw fail("proven failure was not reported") }
    guard try retry.printJob(jobBody("k1", opaque)) == "retry-2" else { throw fail("retry after notSent") }
    guard (try? retry.printJob(jobBody("broken", Data(pngPrefix) + Data("x".utf8)))) == nil, attempt == 2,
          (try? retry.printJob(jobBody("broken", Data(pngPrefix) + Data("x".utf8)))) == nil, attempt == 2 else {
        throw fail("undecodable PNG reached the printer")
    }
    // Memory rollback when the first journal write fails.
    var sent = 0
    let writes = try Printer(
        directory: directory.appendingPathComponent("writes"),
        submit: { _, _, _, mark in try mark(); sent += 1; return "w-\(sent)" }, queue: { "test-printer" })
    let store = directory.appendingPathComponent("writes/direct-jobs.json")
    try? FileManager.default.removeItem(at: store)
    try FileManager.default.createDirectory(at: store, withIntermediateDirectories: false)
    if (try? writes.printJob(jobBody("w1", opaque))) != nil || sent != 0 { throw fail("write failure") }
    try FileManager.default.removeItem(at: store)
    guard try writes.printJob(jobBody("w1", opaque)) == "w-1", sent == 1 else { throw fail("rollback of memory state") }

    // The journal of the previous Python release keeps protecting its keys.
    let legacyDirectory = directory.appendingPathComponent("legacy")
    try FileManager.default.createDirectory(at: legacyDirectory, withIntermediateDirectories: true)
    var database: OpaquePointer?
    let hash = SHA256.hash(data: opaque).map { String(format: "%02x", $0) }.joined()
    guard sqlite3_open(legacyDirectory.appendingPathComponent("direct-jobs.sqlite3").path, &database) == SQLITE_OK,
          sqlite3_exec(database, "CREATE TABLE jobs (id TEXT PRIMARY KEY, hash TEXT, receipt TEXT);"
                       + "INSERT INTO jobs VALUES ('old-key', '\(hash)', 'Old-5');"
                       + "INSERT INTO jobs VALUES ('old-open', '\(hash)', NULL);", nil, nil, nil) == SQLITE_OK else {
        throw fail("legacy fixture")
    }
    sqlite3_close(database)
    var legacySent = 0
    let migrated = try Printer(directory: legacyDirectory,
                               submit: { _, _, _, mark in try mark(); legacySent += 1; return "new" }, queue: { "test-printer" })
    guard try migrated.printJob(jobBody("old-key", opaque)) == "Old-5", legacySent == 0,
          (try? migrated.printJob(jobBody("old-open", opaque))) == nil, legacySent == 0,
          try Printer(directory: legacyDirectory, submit: { _, _, _, _ in "x" }, queue: { "q" })
              .printJob(jobBody("old-key", opaque)) == "Old-5" else { throw fail("legacy import") }

    // A tool that ignores SIGTERM is killed; the output pipe is drained meanwhile.
    let started = Date()
    let stuck = try run("/bin/sh", ["-c", "trap '' TERM; exec sleep 30"], timeout: 0.3, grace: 0.3)
    guard stuck.timedOut, Date().timeIntervalSince(started) < 5 else { throw fail("hung process was not stopped") }
    let big = try run("/usr/bin/head", ["-c", "400000", "/dev/zero"], timeout: 10)
    guard !big.timedOut, big.status == 0, big.output.utf8.count == 400_000 else { throw fail("pipe draining") }
    do { _ = try run("/nonexistent/lp", [], timeout: 1); throw fail("launch error") } catch PrintError.notSent { }

    // Exact queue media only; otherwise the queue keeps its own default.
    let listing = "PageSize/Media Size: A4 Letter 58x80mm *58x40mm.Borderless 100x150mm\nDuplex/Sides: *None"
    guard matchMedia(listing, width: 58, height: 40) == "58x40mm.Borderless",
          matchMedia(listing.replacingOccurrences(of: "58x40mm.Borderless", with: "58x40mm 58x40mm.Borderless"),
                     width: 58, height: 40) == "58x40mm",
          matchMedia(listing, width: 40, height: 58) == nil,
          matchMedia(listing, width: 100, height: 150) == "100x150mm",
          matchMedia(listing, width: 58.0, height: 41) == nil,
          matchMedia("PageSize/Media Size: 58x40mm.Borderless 60x40mm.Borderless 60x80mm.Borderless 70x120mm.Borderless",
                     width: 58, height: 40) == "58x40mm.Borderless" else { throw fail("media match") }

    // PNG checks: damaged data is refused, transparency is painted on white.
    guard (try? preparePNG(Data(opaque.prefix(opaque.count - 20)))) == nil,
          (try? preparePNG(Data(opaque.prefix(opaque.count / 2)))) == nil,
          (try? preparePNG(Data(pngPrefix))) == nil else { throw fail("damaged PNG accepted") }
    guard try preparePNG(opaque) == opaque else { throw fail("opaque PNG was changed") }
    let glass = try preparePNG(testPNG(width: 4, height: 4, alpha: 0))
    let half = try preparePNG(testPNG(width: 4, height: 4, alpha: 255))
    guard firstPixel(glass, row: 0) == [255, 255, 255, 255], firstPixel(half, row: 0) == [0, 0, 0, 255] ||
          firstPixel(half, row: 3) == [0, 0, 0, 255] else { throw fail("transparent background") }
    print("WMS Print Direct macOS: package OK")
}

/// Asks whatever listens on the port who it is.  True only for WMS Print itself.
private func liveInstance(attempts: Int) -> Bool {
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
                   value["app"] as? String == appName { return true }
            }
        }
        if attempt + 1 < attempts { Thread.sleep(forTimeInterval: 0.3) }
    }
    return false
}

private var instanceLock: Int32 = -1  // held until the process ends; the OS drops it on a crash too

private func runServer() throws {
    signal(SIGPIPE, SIG_IGN)
    let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    let directory = appSupport.appendingPathComponent("WMS Print/direct")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    instanceLock = open(directory.appendingPathComponent("instance.lock").path, O_CREAT | O_RDWR, 0o600)
    if instanceLock >= 0, flock(instanceLock, LOCK_EX | LOCK_NB) != 0 {
        // Opened twice: the first copy is working, so stay quiet and succeed.
        if liveInstance(attempts: 10) {
            print("WMS Print уже запущена и работает. Это окно можно закрыть.")
            return
        }
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
        if liveInstance(attempts: 3) {  // an older copy that predates the lock file
            print("WMS Print уже запущена и работает. Это окно можно закрыть.")
            return
        }
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
