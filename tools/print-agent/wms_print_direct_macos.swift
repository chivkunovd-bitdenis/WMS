import CryptoKit
import Darwin
import Foundation

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

private enum PrintError: Error, CustomStringConvertible {
    case message(String)

    var description: String {
        switch self {
        case .message(let value): return value
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

private func run(
    _ executable: String, _ arguments: [String], timeout: TimeInterval,
    mergeStandardError: Bool = true
) throws -> ProcessResult {
    let process = Process()
    let pipe = Pipe()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    process.environment = ProcessInfo.processInfo.environment.merging(["LC_ALL": "C"]) { _, new in new }
    process.standardOutput = pipe
    // Resolver output is data: a warning on stderr is not part of a queue name.
    // Keep diagnostics in the helper's terminal without mixing them into stdout.
    process.standardError = mergeStandardError ? pipe : FileHandle.standardError

    let timeoutLock = NSLock()
    var timedOut = false
    try process.run()
    let timeoutWork = DispatchWorkItem {
        timeoutLock.lock()
        timedOut = true
        timeoutLock.unlock()
        if process.isRunning { process.terminate() }
    }
    DispatchQueue.global().asyncAfter(deadline: .now() + timeout, execute: timeoutWork)
    process.waitUntilExit()
    timeoutWork.cancel()
    let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    timeoutLock.lock()
    let didTimeOut = timedOut
    timeoutLock.unlock()
    return ProcessResult(status: process.terminationStatus, output: output, timedOut: didTimeOut)
}

private func defaultPrinter() throws -> String {
    let result = try run("/usr/bin/lpstat", ["-d"], timeout: 5, mergeStandardError: false)
    guard !result.timedOut else {
        throw PrintError.message("Служба печати macOS не ответила вовремя. Этикетка не отправлена; повторите скан после восстановления печати.")
    }
    if result.status == 0, let separator = result.output.firstIndex(of: ":") {
        let name = result.output[result.output.index(after: separator)...].trimmingCharacters(in: .whitespacesAndNewlines)
        if !name.isEmpty, name.count <= 127, !name.contains(where: { $0.isWhitespace }) {
            // lpstat -d may return exit 0 and an error containing a colon.
            // Validate the exact queue before Printer persists an uncertain job.
            let queue = try run("/usr/bin/lpstat", ["-p", name], timeout: 5, mergeStandardError: false)
            if !queue.timedOut, queue.status == 0 { return name }
        }
    }
    let printers = try run("/usr/bin/lpstat", ["-p"], timeout: 5, mergeStandardError: false)
    guard !printers.timedOut, printers.status == 0 else {
        throw PrintError.message("Недоступна служба печати macOS или список её принтеров. Этикетка не отправлена; проверьте печать в macOS и повторите скан.")
    }
    throw PrintError.message("macOS не определила принтер по умолчанию. В настройках «Принтеры и сканеры» выберите конкретный принтер этикеток, затем повторите скан. Этикетка не отправлена.")
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

private func submitToDefaultPrinter(_ data: Data, queue: String) throws -> String {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("wms-qr-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let label = directory.appendingPathComponent("label.png")
    try data.write(to: label, options: .atomic)
    let result = try run(
        "/usr/bin/lp",
        ["-d", queue, "-o", "fit-to-page", "-o", "copies=1", "--", label.path],
        timeout: 60
    )
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

private final class Printer {
    private let lock = NSLock()
    private let storeURL: URL
    private let submit: (Data, String) throws -> String
    private let queue: () throws -> String
    private var jobs: [String: StoredJob]

    init(
        directory: URL,
        submit: @escaping (Data, String) throws -> String = submitToDefaultPrinter,
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

        lock.lock()
        defer { lock.unlock() }
        if let old = jobs[key] {
            guard old.hash == digest else { throw PrintError.message("Содержимое этого задания изменилось") }
            guard let receipt = old.receipt else {
                throw PrintError.message("Задание уже передавалось. Проверьте очередь принтера; повтор автоматически не отправлен.")
            }
            return receipt
        }

        let queue = try queue()
        jobs[key] = StoredJob(hash: digest, receipt: nil)
        try persist()
        let receipt = try submit(data, queue)
        jobs[key] = StoredJob(hash: digest, receipt: receipt)
        try persist()
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
                respond(descriptor, status: 200, value: ["app": "WMS Print Direct", "printer": try defaultPrinter()], origin: origin)
            } catch {
                respond(descriptor, status: 503, value: ["app": "WMS Print Direct", "error": String(describing: error)], origin: origin)
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

private func runSelfTest() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("wms-print-self-test-\(UUID().uuidString)")
    defer { try? FileManager.default.removeItem(at: directory) }
    var submissions = 0
    let printer = try Printer(
        directory: directory,
        submit: { _, _ in submissions += 1; return "test-1" },
        queue: { "test-printer" }
    )
    let image = "data:image/png;base64," + pngPrefix.base64EncodedString()
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
    print("WMS Print Direct macOS: package OK")
}

private func runServer() throws {
    signal(SIGPIPE, SIG_IGN)
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
        throw PrintError.message("WMS Print уже запущена либо локальный порт занят")
    }
    let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    let printer = try Printer(directory: appSupport.appendingPathComponent("WMS Print/direct"))
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
