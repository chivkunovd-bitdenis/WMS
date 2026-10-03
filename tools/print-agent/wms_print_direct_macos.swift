import CryptoKit
import Darwin
import Foundation
import ImageIO

@_silgen_name("wms_cups_observe")
private func cupsObserve(_ queue: UnsafePointer<CChar>, _ receipt: UnsafePointer<CChar>, _ title: UnsafePointer<CChar>) -> Int32
private let port = UInt16(ProcessInfo.processInfo.environment["WMS_PRINT_PORT"] ?? "") ?? 17843
private let localOrigin = "http://127.0.0.1:\(port)"
private let allowedOrigins: Set<String> = [localOrigin, "https://sellerfocus.pro", "https://www.sellerfocus.pro", "https://wms.sellerfocus.pro", "https://web-production-9e7c1.up.railway.app"]
private let pngPrefix = Data([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a])
private enum PrintError: Error, CustomStringConvertible {
    case message(String)
    case beforeSubmit(String)
    var description: String { switch self { case .message(let s), .beforeSubmit(let s): return s } }
}
private func digest(_ data: Data) -> String { SHA256.hash(data:data).map { String(format:"%02x", $0) }.joined() }
private func now() -> String { ISO8601DateFormatter().string(from:Date()) }
private func millimeters(_ value: Double) -> String {
    value.rounded() == value ? String(Int(value)) : String(format:"%.2f",locale:Locale(identifier:"en_US_POSIX"),value)
}
private func labelSize(_ body: [String:Any]) throws -> (Double,Double) {
    guard let w=body["widthMm"] as? NSNumber, let h=body["heightMm"] as? NSNumber,
          CFGetTypeID(w) != CFBooleanGetTypeID(), CFGetTypeID(h) != CFBooleanGetTypeID(),
          w.doubleValue.isFinite, h.doubleValue.isFinite,
          (10...300).contains(w.doubleValue), (10...300).contains(h.doubleValue) else {
        throw PrintError.message("WMS не передала корректный размер этикетки")
    }
    return (w.doubleValue,h.doubleValue)
}
// A complete file is fsynced before rename, then its parent directory is fsynced.
// Memory is updated only after this succeeds; failures can never authorize lp.
private func durableWrite(_ data: Data, _ url: URL) throws {
    let temporary = url.deletingLastPathComponent().appendingPathComponent(".\(UUID().uuidString).tmp")
    let fd = Darwin.open(temporary.path, O_WRONLY|O_CREAT|O_EXCL, mode_t(0o600))
    guard fd >= 0 else { throw PrintError.message("Не удалось сохранить задание: \(String(cString:strerror(errno)))") }
    defer { Darwin.close(fd); try? FileManager.default.removeItem(at:temporary) }
    try data.withUnsafeBytes { bytes in
        var offset=0
        while offset<data.count {
            let n=Darwin.write(fd,bytes.baseAddress!.advanced(by:offset),data.count-offset)
            if n<0 && errno == EINTR { continue }
            guard n>0 else { throw PrintError.message("Не удалось записать задание на диск") }
            offset += n
        }
    }
    guard fsync(fd)==0, fcntl(fd,F_FULLFSYNC)==0 else { throw PrintError.message("Диск не подтвердил сохранение задания") }
    guard rename(temporary.path,url.path)==0 else { throw PrintError.message("Не удалось сохранить журнал задания") }
    let parent=Darwin.open(url.deletingLastPathComponent().path,O_RDONLY)
    guard parent>=0 else { throw PrintError.message("Не удалось открыть каталог журнала") }
    defer { Darwin.close(parent) }
    guard fsync(parent)==0 else { throw PrintError.message("Каталог журнала не сохранён") }
}
private struct ProcessResult { let status:Int32; let output:String; let timedOut:Bool }
private func run(_ executable:String,_ arguments:[String],timeout:TimeInterval) throws -> ProcessResult {
    let process=Process();let pipe=Pipe()
    process.executableURL=URL(fileURLWithPath:executable);process.arguments=arguments
    process.environment=ProcessInfo.processInfo.environment.merging(["LC_ALL":"C"]) { _,new in new }
    process.standardOutput=pipe;process.standardError=pipe
    let ended=DispatchSemaphore(value:0);process.terminationHandler={ _ in ended.signal() }
    do { try process.run() } catch { throw PrintError.beforeSubmit("Системная команда не запустилась: \(error)") }
    pipe.fileHandleForWriting.closeFile()
    let fd=pipe.fileHandleForReading.fileDescriptor
    _=fcntl(fd,F_SETFL,fcntl(fd,F_GETFL)|O_NONBLOCK)
    final class Capture { let lock=NSLock();var data=Data();var stop=false }
    let capture=Capture();let readerDone=DispatchSemaphore(value:0)
    DispatchQueue.global().async {
        var buffer=[UInt8](repeating:0,count:8192)
        while true {
            let n=Darwin.read(fd,&buffer,buffer.count)
            capture.lock.lock()
            if n>0 && capture.data.count<1_000_000 { capture.data.append(contentsOf:buffer.prefix(min(n,1_000_000-capture.data.count))) }
            let stop=capture.stop;capture.lock.unlock()
            if n==0 || stop { break }
            if n<0 { if errno != EAGAIN && errno != EINTR { break };Thread.sleep(forTimeInterval:0.005) }
        }
        readerDone.signal()
    }
    let timedOut=ended.wait(timeout:.now()+timeout) == .timedOut
    if timedOut {
        if process.isRunning { process.terminate() }
        if ended.wait(timeout:.now()+0.25) == .timedOut {
            if process.isRunning { kill(process.processIdentifier,SIGKILL) }
            _=ended.wait(timeout:.now()+2)
        }
    }
    capture.lock.lock();capture.stop=true;capture.lock.unlock()
    // A descendant retaining stdout cannot hold the server after its parent exits.
    readerDone.wait()
    pipe.fileHandleForReading.closeFile()
    capture.lock.lock();let data=capture.data;capture.lock.unlock()
    return ProcessResult(status:process.isRunning ? -1:process.terminationStatus,output:String(data:data,encoding:.utf8) ?? "",timedOut:timedOut)
}
private func defaultPrinter() throws -> String {
    let result=try run("/usr/bin/lpstat",["-d"],timeout:5)
    guard !result.timedOut,result.status==0,let i=result.output.firstIndex(of:":") else { throw PrintError.beforeSubmit("В системе не выбран принтер по умолчанию") }
    let name=result.output[result.output.index(after:i)...].trimmingCharacters(in:.whitespacesAndNewlines)
    guard !name.isEmpty,name.count<=127,!name.contains(where:{$0.isWhitespace || $0=="/" || $0=="\\"}) else { throw PrintError.beforeSubmit("Некорректная системная очередь") }
    return name
}
private func parseReceipt(_ output:String,queue:String) -> String? {
    let pattern="(?<![A-Za-z0-9_.-])"+NSRegularExpression.escapedPattern(for:queue)+"-[0-9]+(?![A-Za-z0-9_.-])"
    guard let re=try? NSRegularExpression(pattern:pattern) else { return nil }
    let matches=re.matches(in:output,range:NSRange(output.startIndex...,in:output))
    let values=Set(matches.compactMap { Range($0.range,in:output).map { String(output[$0]) } })
    return values.count==1 ? values.first : nil
}
private enum ContextValue: Codable, Equatable {
    case string(String), number(Double)
    init(from decoder: Decoder) throws {
        let c=try decoder.singleValueContainer()
        if let s=try? c.decode(String.self) { self = .string(s) } else { self = .number(try c.decode(Double.self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c=encoder.singleValueContainer()
        switch self { case .string(let s):try c.encode(s);case .number(let n):try c.encode(n) }
    }
}
private struct StoredJob: Codable, Equatable {
    var idempotencyKey:String
    var hash:String
    var receipt:String?
    var queue:String?
    var widthMm:Double?
    var heightMm:Double?
    var context:[String:ContextValue] = [:]
    var createdAt:String
    var updatedAt:String
    var status:String
    var reason:String
    var title:String?
    var legacy:Bool = false
    var parentKey:String?
    var duplicateRiskAcknowledged:Bool?
    var reprintIntentKeys:[String]?
    var observations:[String] = []
    var queueObservation:[String:String] = [:]
}
/// The record format of v2026.09.30.4 (`StoredJob { hash; receipt? }` in direct-jobs.json).
/// `v2` marks this program's own mirrored jobs; .4 ignores the field (and drops it when it
/// rewrites the file), so an entry without it was written or rewritten by the older program.
private struct LegacyEntry: Codable, Equatable {
    var hash:String
    var receipt:String?
    var v2:Bool?
}
private func printArguments(queue:String,label:String,width:Double,height:Double,title:String) -> [String] {
    ["-d",queue,"-t",title,"-o","media=Custom.\(millimeters(width))x\(millimeters(height))mm","-o","fit-to-page","-o","copies=1","--",label]
}
private func submitToDefaultPrinter(_ job:StoredJob,_ image:URL) throws -> String {
    let result=try run("/usr/bin/lp",printArguments(queue:job.queue!,label:image.path,width:job.widthMm!,height:job.heightMm!,title:job.title!),timeout:12)
    guard !result.timedOut,result.status==0,let receipt=parseReceipt(result.output,queue:job.queue!) else {
        throw PrintError.message("Исход передачи неизвестен; \(result.timedOut ? "таймаут" : "код \(result.status)"). \(result.output.prefix(1000))")
    }
    return receipt
}
private func observeQueue(_ job:StoredJob) throws -> [String:Any] {
    guard let queue=job.queue else { return ["error":"Сохранённая очередь отсутствует"] }
    guard job.title != nil else { return ["error":"Старое задание не имеет уникального имени; исход по одному номеру квитанции не устанавливается"] }
    let executable=URL(fileURLWithPath:CommandLine.arguments[0]).standardizedFileURL.path
    let result=try run(executable,["--observe",queue,job.receipt ?? "",job.title ?? ""],timeout:8)
    guard !result.timedOut,result.status==0,let data=result.output.data(using:.utf8),let value=try JSONSerialization.jsonObject(with:data) as? [String:Any] else { throw PrintError.message("Наблюдение CUPS недоступно или превысило время ожидания") }
    return value
}
private final class Printer {
    private let lock=NSRecursiveLock()
    private let directory:URL
    private let records:URL
    private let submit:(StoredJob,URL) throws -> String
    private let queue:() throws -> String
    private let write:(Data,URL) throws -> Void
    /// The older journal is written the way v2026.09.30.4 wrote it (atomic replace, no full
    /// fsync): it is a rollback safety net and must not slow every label down.
    private let legacyWrite:(Data,URL) throws -> Void
    private let beforeRelease:() -> Void
    private let observe:(StoredJob) throws -> [String:Any]
    private let worker=DispatchQueue(label:"wms-print-submit")
    private let observer=DispatchQueue(label:"wms-print-observe")
    private var jobs:[String:StoredJob]=[:]
    /// WMS-625: the journal of v2026.09.30.4 (direct-jobs.json, key -> hash and receipt).
    /// Every job this program hands to the queue is mirrored there before lp, so the
    /// older program, if it is started again, returns the same receipt or refuses
    /// a repeat of the key instead of printing a second label.
    private var legacyEntries:[String:LegacyEntry]=[:]
    private let legacyURL:URL
    private var active=Set<String>()
    private var observing=Set<String>()
    private var blocked=Set<String>()
    private var storageError:String?
    private var lockFD:Int32 = -1
    private var autoWork:Bool
    var diagnostics:[String]=[]

    init(directory:URL,autoWork:Bool=true,
         submit:@escaping (StoredJob,URL) throws -> String=submitToDefaultPrinter,
         queue:@escaping () throws -> String=defaultPrinter,
         write:@escaping (Data,URL) throws -> Void=durableWrite,
         legacyWrite:@escaping (Data,URL) throws -> Void={ data,url in try data.write(to:url,options:.atomic) },
         beforeRelease:@escaping () -> Void={},
         observe:@escaping (StoredJob) throws -> [String:Any]=observeQueue) throws {
        self.directory=directory; self.records=directory.appendingPathComponent("jobs-v2"); self.legacyURL=directory.appendingPathComponent("direct-jobs.json"); self.submit=submit;self.queue=queue;self.write=write;self.legacyWrite=legacyWrite;self.beforeRelease=beforeRelease;self.observe=observe;self.autoWork=autoWork
        try FileManager.default.createDirectory(at:records,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        lockFD=Darwin.open(directory.appendingPathComponent("runtime.lock").path,O_CREAT|O_RDWR,mode_t(0o600))
        guard lockFD>=0,flock(lockFD,LOCK_EX|LOCK_NB)==0 else { if lockFD>=0 { Darwin.close(lockFD);lockFD = -1 };throw PrintError.message("Журнал уже открыт другой программой WMS Print") }
        let legacy=legacyURL
        if FileManager.default.fileExists(atPath:legacy.path) {
            do {
                let map=try JSONSerialization.jsonObject(with:Data(contentsOf:legacy)) as? [String:[String:Any]]
                guard let map else { throw PrintError.message("Некорректный старый журнал") }
                for (key,value) in map {
                    guard let hash=value["hash"] as? String else { throw PrintError.message("Некорректная старая запись") }
                    let receipt=value["receipt"] as? String
                    let mirrored=value["v2"] as? Bool == true
                    legacyEntries[key]=LegacyEntry(hash:hash,receipt:receipt,v2:mirrored ? true:nil)
                    // This program's own job lives in jobs-v2; its mirror is not an older-program record.
                    if mirrored { continue }
                    let queue=receipt.flatMap { value in value.lastIndex(of:"-").map { String(value[..<$0]) } }
                    jobs[key]=StoredJob(idempotencyKey:key,hash:hash,receipt:receipt,queue:queue,createdAt:"unknown",updatedAt:now(),status:receipt == nil ? "unknown":"accepted",reason:"Старый журнал: изображение, размер и физический результат отсутствуют",legacy:true)
                }
            } catch { storageError="Старый журнал повреждён; новая печать остановлена для защиты от дублей";diagnostics.append(storageError!) }
        }
        for file in try FileManager.default.contentsOfDirectory(at:records,includingPropertiesForKeys:nil) where file.pathExtension == "json" {
            do {
                var job=try JSONDecoder().decode(StoredJob.self,from:Data(contentsOf:file))
                guard file.deletingPathExtension().lastPathComponent == digest(Data(job.idempotencyKey.utf8)) else { throw PrintError.message("Ключ журнала не совпадает") }
                guard ["saved","submitting","unknown","accepted","pending","held","processing","stopped","canceled","aborted","completed","failed_before_submit"].contains(job.status),
                      !job.idempotencyKey.isEmpty,job.hash.count==64,job.hash.allSatisfy({$0.isHexDigit}) else { throw PrintError.message("Некорректная запись задания") }
                if !job.legacy {
                    guard let w=job.widthMm,let h=job.heightMm,w.isFinite,h.isFinite,(10...300).contains(w),(10...300).contains(h),job.title == "WMS-"+digest(Data((job.idempotencyKey+"|"+job.hash).utf8)) else { throw PrintError.message("Повреждены размер или имя задания") }
                }
                if job.status == "submitting" { job.status="unknown";job.reason="Программа завершилась во время передачи; требуется сверка очереди" }
                jobs[job.idempotencyKey]=job
            } catch { blocked.insert(file.deletingPathExtension().lastPathComponent);diagnostics.append("Повреждена запись \(file.lastPathComponent); исходник сохранён") }
        }
        // WMS-625: the older program may have run between two runs of this one and printed
        // a job this one had only saved. Its own receipt (or its unfinished attempt) wins:
        // a saved job is never handed to the queue a second time.
        for (key,job) in jobs where !job.legacy && job.status == "saved" {
            guard let old=legacyEntries[key],old.v2 != true,old.hash==job.hash else { continue }
            let merged = old.receipt.map { receipt -> StoredJob in var accepted=job;accepted.receipt=receipt;return change(accepted,status:"accepted",reason:"Задание приняла предыдущая версия WMS Print; бумага не подтверждена") }
                ?? change(job,status:"unknown",reason:"Предыдущая версия WMS Print начала передачу и не записала результат; требуется сверка очереди")
            do { try persist(merged) } catch { blocked.insert(digest(Data(key.utf8)));diagnostics.append("Не удалось сохранить итог предыдущей версии для \(key); повтор защищён") }
        }
        // An orphan image may be an interrupted enqueue OR a lost metadata file from
        // an already submitted job. After restart those cases cannot be distinguished.
        // A key known only from the older journal (mirrored there before lp) does not explain its v2 PNG.
        let knownFiles=Set(jobs.values.filter { !$0.legacy }.map { digest(Data($0.idempotencyKey.utf8)) })
        for file in try FileManager.default.contentsOfDirectory(at:records,includingPropertiesForKeys:nil) where file.pathExtension == "png" {
            let name=file.deletingPathExtension().lastPathComponent
            if !knownFiles.contains(name) && !blocked.contains(name) {
                blocked.insert(name)
                diagnostics.append("Для PNG \(file.lastPathComponent) отсутствует описание; исход неизвестен, повтор защищён")
            }
        }
        // Saved means no irreversible call began. Only this state resumes automatically.
        if autoWork { for job in jobs.values where job.status == "saved" { schedule(job.idempotencyKey) } }
    }
    deinit { if lockFD>=0 { flock(lockFD,LOCK_UN);Darwin.close(lockFD) } }
    private func imageURL(_ key:String) -> URL { records.appendingPathComponent(digest(Data(key.utf8))+".png") }
    /// Written before memory; .4 decodes [key: {hash, receipt?}].
    private func mirrorLegacy(_ key:String,hash:String,receipt:String?) throws {
        var next=legacyEntries;next[key]=LegacyEntry(hash:hash,receipt:receipt,v2:true)
        try legacyWrite(JSONEncoder().encode(next),legacyURL)
        legacyEntries=next
    }
    private func forgetLegacy(_ key:String) {
        guard legacyEntries[key] != nil else { return }
        var next=legacyEntries;next.removeValue(forKey:key)
        do { try legacyWrite(JSONEncoder().encode(next),legacyURL);legacyEntries=next } catch { diagnostics.append("Не удалось убрать неотправленное задание \(key) из журнала старой версии") }
    }
    private func persist(_ job:StoredJob) throws {
        try write(JSONEncoder().encode(job),records.appendingPathComponent(digest(Data(job.idempotencyKey.utf8))+".json"))
        jobs[job.idempotencyKey]=job
    }
    private func writable(_ key:String) throws {
        if let error=storageError { throw PrintError.message(error) }
        guard !blocked.contains(digest(Data(key.utf8))) else { throw PrintError.message("Запись этого задания повреждена; исходные файлы сохранены") }
    }
    private func change(_ job:StoredJob,status:String,reason:String) -> StoredJob {
        var result=job;result.status=status;result.reason=reason;result.updatedAt=now();if status != job.status || reason != job.reason { result.observations.append("\(result.updatedAt) \(status): \(reason)") };return result
    }
    private func publicValue(_ job:StoredJob) throws -> [String:Any] {
        var value=try JSONSerialization.jsonObject(with:JSONEncoder().encode(job)) as! [String:Any]
        value["paperStatus"]="unconfirmed"
        value["imageAvailable"] = !job.legacy && FileManager.default.fileExists(atPath:imageURL(job.idempotencyKey).path)
        value["physicalConfirmationSupported"]=false
        return value
    }
    func detail(_ key:String,includeReprints:Bool=true) throws -> [String:Any]? {
        lock.lock();defer{lock.unlock()}
        if blocked.contains(digest(Data(key.utf8))) { throw PrintError.message("Запись задания повреждена; повтор запрещён, исходник сохранён") }
        guard let job=jobs[key] else { if let e=storageError { throw PrintError.message(e) };return nil }
        var value=try publicValue(job)
        if includeReprints {
            var children=try jobs.values.filter { $0.parentKey==key && !blocked.contains(digest(Data($0.idempotencyKey.utf8))) }.sorted { $0.createdAt<$1.createdAt }.map { try publicValue($0) }
            let found=Set(children.compactMap { $0["idempotencyKey"] as? String })
            for child in job.reprintIntentKeys ?? [] where !found.contains(child) {
                children.append(["idempotencyKey":child,"parentKey":key,"hash":job.hash,"status":"unknown","reason":"Сохранено намерение повторной печати, но описание дочернего задания недоступно; автоматического повтора нет","paperStatus":"unconfirmed","imageAvailable":false,"legacy":false])
            }
            value["reprints"]=children
        }
        return value
    }
    func list() throws -> [String:Any] {
        lock.lock();defer{lock.unlock()}
        return ["jobs":try jobs.values.filter{!blocked.contains(digest(Data($0.idempotencyKey.utf8)))}.sorted{$0.updatedAt>$1.updatedAt}.compactMap{try detail($0.idempotencyKey,includeReprints:false)},"diagnostics":diagnostics]
    }
    func image(_ key:String) throws -> Data {
        lock.lock();defer{lock.unlock()}
        guard let job=jobs[key],!job.legacy else { throw PrintError.message("Исходное изображение отсутствует в старом журнале") }
        let data=try Data(contentsOf:imageURL(key))
        guard let width=job.widthMm,let height=job.heightMm else { throw PrintError.message("Размер сохранённого задания отсутствует") }
        var identity=data;identity.append(Data("|\(width)x\(height)".utf8))
        guard digest(identity)==job.hash else { throw PrintError.message("Сохранённое изображение повреждено; повтор запрещён") }
        return data
    }
    func printJob(_ body:[String:Any],parent:String?=nil,scheduleNow:Bool=true) throws -> [String:Any] {
        guard let key=body["idempotencyKey"] as? String,(1...200).contains(key.count),let image=body["imageDataUrl"] as? String,image.hasPrefix("data:image/png;base64,"),let data=Data(base64Encoded:String(image.dropFirst(22))),data.count<=4_000_000,data.starts(with:pngPrefix),
              let source=CGImageSourceCreateWithData(data as CFData,nil),
              let properties=CGImageSourceCopyPropertiesAtIndex(source,0,nil) as? [CFString:Any],
              let pixelWidth=properties[kCGImagePropertyPixelWidth] as? NSNumber,let pixelHeight=properties[kCGImagePropertyPixelHeight] as? NSNumber,
              pixelWidth.doubleValue>0,pixelHeight.doubleValue>0,pixelWidth.doubleValue*pixelHeight.doubleValue<=20_000_000,
              CGImageSourceCreateImageAtIndex(source,0,nil) != nil else { throw PrintError.message("Ожидается корректная PNG-этикетка и ключ операции") }
        let (w,h)=try labelSize(body);var identity=data;identity.append(Data("|\(w)x\(h)".utf8));let hash=digest(identity)
        lock.lock();defer{lock.unlock()};try writable(key)
        if let old=jobs[key] {
            guard old.hash==hash || (old.legacy && old.hash==digest(data)) else { throw PrintError.message("Содержимое или размер этого задания изменились") }
            guard old.parentKey==parent else { throw PrintError.message("Ключ принадлежит другой операции восстановления") }
            return try detail(key)!
        }
        guard !jobs.values.contains(where: { ($0.reprintIntentKeys ?? []).contains(key) }) else {
            throw PrintError.message("Исход повторной операции неизвестен: её описание утрачено. Прежний ключ повторно не отправлен")
        }
        var context:[String:ContextValue]=[:]
        if let supplied=body["context"] as? [String:Any] {
            for name in ["tenantId","userId","wbOrderId","scanId","orderId","supplyId","marketplace","productId","barcode","orderNumber","sellerId","sellerName","scan_id","order_id","supply_id"] {
                if let value=supplied[name] as? String { context[name] = .string(String(value.prefix(500))) }
                else if let value=supplied[name] as? NSNumber { context[name] = .number(value.doubleValue) }
            }
        }
        let timestamp=now()
        let job=StoredJob(idempotencyKey:key,hash:hash,widthMm:w,heightMm:h,context:context,createdAt:timestamp,updatedAt:timestamp,status:"saved",reason:"Изображение сохранено; ожидает передачи в системную очередь",title:"WMS-"+digest(Data((key+"|"+hash).utf8)),parentKey:parent,duplicateRiskAcknowledged:parent == nil ? nil:true,observations:["\(timestamp) saved" + (parent == nil ? "":"; оператор явно подтвердил риск повторной этикетки")])
        try write(data,imageURL(key));try persist(job)
        if autoWork && scheduleNow { schedule(key) }
        return try detail(key)!
    }
    private func schedule(_ key:String) {
        lock.lock();defer{lock.unlock()}
        guard !active.contains(key) else { return };active.insert(key)
        worker.async { self.process(key);self.beforeRelease();self.lock.lock();self.active.remove(key);if self.jobs[key]?.status == "saved" && self.storageError == nil { self.schedule(key) };self.lock.unlock() }
    }
    private func ensureParentIntent(_ job:StoredJob) throws {
        guard let parentKey=job.parentKey else { return }
        try writable(parentKey)
        guard var parent=jobs[parentKey] else { throw PrintError.beforeSubmit("Исходное задание восстановления недоступно") }
        if !(parent.reprintIntentKeys ?? []).contains(job.idempotencyKey) {
            parent.reprintIntentKeys=(parent.reprintIntentKeys ?? [])+[job.idempotencyKey]
            parent.updatedAt=now()
            parent.observations.append("\(parent.updatedAt) explicit-reprint: \(job.idempotencyKey); оператор подтвердил риск дубликата")
            try persist(parent)
        }
    }
    func process(_ key:String) {
        lock.lock()
        guard var job=jobs[key],job.status=="saved",(try? writable(key)) != nil else { lock.unlock();return }
        lock.unlock()
        do {
            // Nothing external has started yet: failures here remain safely retryable.
            _=try image(key);job.queue=try queue()
            lock.lock()
            do {
                try ensureParentIntent(job);job=change(job,status:"submitting",reason:"Начата передача в системную очередь");try persist(job)
                try mirrorLegacy(key,hash:job.hash,receipt:nil)
            } catch { lock.unlock();throw PrintError.beforeSubmit(String(describing:error)) }
            lock.unlock()
            do {
                let receipt=try submit(job,imageURL(key))
                lock.lock();defer{lock.unlock()}
                job.receipt=receipt;job=change(job,status:"accepted",reason:"Системная очередь приняла задание; бумага не подтверждена")
                do {
                    try persist(job)
                    do { try mirrorLegacy(key,hash:job.hash,receipt:receipt) } catch { diagnostics.append("Квитанция \(key) не записана в журнал старой версии: \(error)") }
                } catch { storageError="Не удалось сохранить результат отправки: \(error)";diagnostics.append(storageError!);jobs[key]=change(job,status:"unknown",reason:storageError!) }
            } catch {
                lock.lock();defer{lock.unlock()}
                let status:String
                if case PrintError.beforeSubmit = error { status="failed_before_submit" } else { status="unknown" }
                do { try persist(change(job,status:status,reason:String(describing:error))) } catch { storageError="Не удалось сохранить ошибку отправки: \(error)";diagnostics.append(storageError!) }
                if status == "failed_before_submit" && storageError == nil { forgetLegacy(key) }
            }
        } catch {
            lock.lock();defer{lock.unlock()}
            do { try persist(change(job,status:"failed_before_submit",reason:String(describing:error)));forgetLegacy(key) } catch { storageError="Запись задания недоступна: \(error)";diagnostics.append(storageError!) }
        }
    }
    func retry(_ key:String) throws -> [String:Any] {
        lock.lock();defer{lock.unlock()};try writable(key)
        guard let job=jobs[key],["saved","failed_before_submit"].contains(job.status),!job.legacy,(job.reprintIntentKeys ?? []).isEmpty,!jobs.values.contains(where:{$0.parentKey==key}) else { throw PrintError.message("Исход может быть неизвестен; сначала сверьте очередь. Автоматического повтора нет") }
        _=try image(key);try persist(change(job,status:"saved",reason:"Оператор повторил доказанно неотправленное задание"))
        if autoWork { schedule(key) };return try detail(key)!
    }
    func reprint(_ key:String,body:[String:Any]) throws -> [String:Any] {
        lock.lock();defer{lock.unlock()};try writable(key)
        guard let original=jobs[key],!original.legacy,body["acknowledgeDuplicateRisk"] as? Bool == true,let child=body["idempotencyKey"] as? String,(1...200).contains(child.count),child != key else { throw PrintError.message("Нужны новый ключ и явное подтверждение риска второй этикетки") }
        guard !active.contains(key),original.status != "submitting" else { throw PrintError.message("Передача ещё выполняется; дождитесь результата и сверьте очередь") }
        let data=try image(key)
        try writable(child)
        if let existing=jobs[child],existing.parentKey != key { throw PrintError.message("Ключ принадлежит другой операции восстановления") }
        if jobs[child]==nil && (original.reprintIntentKeys ?? []).contains(child) { throw PrintError.message("Исход повторной операции неизвестен: её описание утрачено. Прежний ключ повторно не отправлен") }
        _=try printJob(["idempotencyKey":child,"imageDataUrl":"data:image/png;base64,"+data.base64EncodedString(),"widthMm":original.widthMm!,"heightMm":original.heightMm!,"context":try JSONSerialization.jsonObject(with:JSONEncoder().encode(original.context))],parent:key,scheduleNow:false)
        try ensureParentIntent(jobs[child]!)
        if autoWork && jobs[child]?.status=="saved" { schedule(child) }
        let result=try detail(child)!
        return result
    }
    func reconcile(_ key:String) throws -> [String:Any] {
        lock.lock();guard let job=jobs[key] else { lock.unlock();throw PrintError.message("Задание не найдено") }
        guard !active.contains(key),!observing.contains(key),!["saved","failed_before_submit"].contains(job.status) else { defer { lock.unlock() };return try detail(key)! }
        observing.insert(key);lock.unlock()
        let observation:[String:Any]
        do { observation=try observe(job) } catch { observation=["error":String(describing:error)] }
        lock.lock();defer{observing.remove(key);lock.unlock()}
        guard let current=jobs[key],current==job else { return try detail(key)! }
        var updated=job
        if let receipt=observation["receipt"] as? String,let state=observation["jobState"] as? Int,observation["matches"] as? Int == 1 {
            updated.receipt=receipt
            updated=change(updated,status:[3:"pending",4:"held",5:"processing",6:"stopped",7:"canceled",8:"aborted",9:"completed"][state] ?? "accepted",reason:"Состояние системной очереди; выход бумаги не подтверждён")
        } else {
            // Missing history never proves non-submission and never authorizes a retry.
            updated=change(updated,status:job.receipt == nil ? "unknown":job.status,reason:observation["error"] as? String ?? "Однозначная запись в очереди отсутствует; прошлый физический исход неизвестен")
        }
        for (k,v) in observation { updated.queueObservation[k]=String(describing:v) }
        do { try persist(updated) } catch { diagnostics.append("Не удалось сохранить наблюдение: \(error)");throw error }
        if !updated.legacy,let receipt=updated.receipt,let old=legacyEntries[key],old.v2 == true,old.receipt == nil {
            do { try mirrorLegacy(key,hash:updated.hash,receipt:receipt) } catch { diagnostics.append("Квитанция \(key) не записана в журнал старой версии: \(error)") }
        }
        return try detail(key)!
    }
    func poll() {
        lock.lock();let keys=jobs.values.filter{!["saved","failed_before_submit","completed","canceled","aborted"].contains($0.status)}.map{$0.idempotencyKey};lock.unlock()
        observer.async { for key in keys { _=try? self.reconcile(key) }; self.observer.asyncAfter(deadline:.now()+15) { self.poll() } }
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
        if headerEnd == nil && received.range(of:delimiter) == nil && received.count>16_384 { throw PrintError.message("HTTP-заголовок слишком большой") }
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

private func respond(_ descriptor:Int32,status:Int,data:Data,type:String="application/json; charset=utf-8",origin:String?) {
    var headers=["HTTP/1.1 \(status) \([200:"OK",202:"Accepted",403:"Forbidden",404:"Not Found",409:"Conflict",503:"Service Unavailable"][status] ?? "Error")","Content-Type: \(type)","Content-Length: \(data.count)","Cache-Control: no-store","Connection: close","X-Content-Type-Options: nosniff"]
    if let origin,allowedOrigins.contains(origin) { headers += ["Access-Control-Allow-Origin: \(origin)","Vary: Origin","Access-Control-Allow-Methods: GET, POST, OPTIONS","Access-Control-Allow-Headers: Content-Type, X-WMS-Print","Access-Control-Allow-Private-Network: true"] }
    sendAll(descriptor,data:Data((headers.joined(separator:"\r\n")+"\r\n\r\n").utf8)+data)
}
private func respond(_ descriptor:Int32,status:Int,value:[String:Any],origin:String?) {
    respond(descriptor,status:status,data:(try? JSONSerialization.data(withJSONObject:value)) ?? Data("{}".utf8),origin:origin)
}
private func handle(_ descriptor:Int32,printer:Printer) {
    defer{Darwin.close(descriptor)}
    var timeout=timeval(tv_sec:20,tv_usec:0)
    setsockopt(descriptor,SOL_SOCKET,SO_RCVTIMEO,&timeout,socklen_t(MemoryLayout.size(ofValue:timeout)))
    setsockopt(descriptor,SOL_SOCKET,SO_SNDTIMEO,&timeout,socklen_t(MemoryLayout.size(ofValue:timeout)))
    var origin:String?
    do {
        let request=try readRequest(descriptor);origin=request.headers["origin"]
        guard request.headers["host"]=="127.0.0.1:\(port)",allowedOrigins.contains(origin ?? localOrigin) else { respond(descriptor,status:403,value:[:],origin:origin);return }
        let parts=request.path.split(separator:"/",omittingEmptySubsequences:true).map(String.init)
        if request.method=="OPTIONS" { respond(descriptor,status:200,value:[:],origin:origin);return }
        if request.method=="GET" {
            if request.path=="/health" { respond(descriptor,status:200,value:["app":"WMS Print Direct","protocolVersion":2,"historyUrl":localOrigin,"physicalConfirmationSupported":false],origin:origin);return }
            if request.path=="/" {
                let url=URL(fileURLWithPath:CommandLine.arguments[0]).standardizedFileURL.deletingLastPathComponent().appendingPathComponent("history.html")
                respond(descriptor,status:200,data:try Data(contentsOf:url),type:"text/html; charset=utf-8",origin:origin);return
            }
            if parts==["jobs"] { respond(descriptor,status:200,value:try printer.list(),origin:origin);return }
            if parts.count>=2,parts[0]=="jobs",let key=parts[1].removingPercentEncoding {
                guard let value=try printer.detail(key) else { respond(descriptor,status:404,value:["error":"Задание не найдено"],origin:origin);return }
                if parts.count==2 { respond(descriptor,status:200,value:value,origin:origin);return }
                if parts.count==3,parts[2]=="image" { respond(descriptor,status:200,data:try printer.image(key),type:"image/png",origin:origin);return }
            }
        }
        if request.method=="POST",request.headers["x-wms-print"]=="1" {
            let body=request.body.isEmpty ? [:] : try JSONSerialization.jsonObject(with:request.body) as? [String:Any]
            guard let body else { throw PrintError.message("Некорректное задание") }
            if request.path=="/print" {
                var result=try printer.printJob(body)
                if body["protocolVersion"] as? Int == 2 { respond(descriptor,status:202,value:result,origin:origin);return }
                // Old browsers require a real OS receipt. Their HTTP lifetime does not own the durable worker.
                let deadline=Date().addingTimeInterval(18)
                while result["receipt"] == nil, ["saved","submitting"].contains(result["status"] as? String ?? ""),Date()<deadline {
                    Thread.sleep(forTimeInterval:0.1);result=try printer.detail(body["idempotencyKey"] as! String)!
                }
                if result["receipt"] == nil || ["held","canceled","aborted","stopped"].contains(result["status"] as? String ?? "") { result["error"]="Задание сохранено, приём очередью не подтверждён. История: \(localOrigin)";respond(descriptor,status:409,value:result,origin:origin) }
                else { respond(descriptor,status:200,value:result,origin:origin) };return
            }
            if parts.count==3,parts[0]=="jobs",let key=parts[1].removingPercentEncoding {
                guard try printer.detail(key) != nil else { respond(descriptor,status:404,value:[:],origin:origin);return }
                let result:[String:Any]
                switch parts[2] {
                case "reconcile":result=try printer.reconcile(key)
                case "retry":result=try printer.retry(key)
                case "reprint":result=try printer.reprint(key,body:body)
                default:respond(descriptor,status:404,value:[:],origin:origin);return
                }
                respond(descriptor,status:200,value:result,origin:origin);return
            }
        }
        respond(descriptor,status:request.method=="POST" ? 403:404,value:[:],origin:origin)
    } catch { respond(descriptor,status:409,value:["error":String(describing:error)],origin:origin) }
}
private let fixturePNG = Data(base64Encoded:"iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGP8//8/AwMDEwMYAAAkBgMBXaJOiAAAAABJRU5ErkJggg==")!
private func fixtureBody(_ key:String) -> [String:Any] {
    ["idempotencyKey":key,"imageDataUrl":"data:image/png;base64,"+fixturePNG.base64EncodedString(),"widthMm":58,"heightMm":40,"context":["orderId":"order-1","tenantId":"tenant-1","userId":"user-1","wbOrderId":456] as [String:Any]]
}
private func runCrashFixture(_ path:String,_ phase:String) throws {
    let root=URL(fileURLWithPath:path)
    let printer=try Printer(directory:root,autoWork:false,submit:{_,_ in
        try durableWrite(Data("test-printer-91".utf8),root.appendingPathComponent("external-receipt"))
        _exit(71)
    },queue:{"test-printer"})
    _=try printer.printJob(fixtureBody("crash"))
    if phase=="saved" { _exit(70) }
    printer.process("crash")
}
private func runSelfTest() throws {
    let root=FileManager.default.temporaryDirectory.appendingPathComponent("wms-test-\(UUID().uuidString)")
    defer{try? FileManager.default.removeItem(at:root)}
    let png=fixturePNG
    func body(_ key:String)->[String:Any] {fixtureBody(key)}
    func check(_ condition:@autoclosure () throws -> Bool,_ message:String) throws {if try !condition(){throw PrintError.message("Self-test: "+message)}}
    var submissions=0
    var printer:Printer?=try Printer(directory:root,autoWork:false,submit:{job,url in
        submissions+=1;try check(try Data(contentsOf:url)==png,"exact image before submit")
        try check(job.queue=="test-printer" && job.widthMm==58 && job.heightMm==40,"dimensions and queue")
        return "test-printer-\(submissions)"
    },queue:{"test-printer"},observe:{job in ["matches":1,"receipt":job.receipt ?? "test-printer-999","jobState":9,"jobStateReasons":["queued-in-device"]]})
    try check(try printer!.printJob(body("one"))["status"] as? String == "saved","durable handoff")
    func olderJournal(_ directory:URL) throws -> [String:LegacyEntry] {
        guard FileManager.default.fileExists(atPath:directory.appendingPathComponent("direct-jobs.json").path) else { return [:] }
        return try JSONDecoder().decode([String:LegacyEntry].self,from:Data(contentsOf:directory.appendingPathComponent("direct-jobs.json")))
    }
    try check(try olderJournal(root)["one"]==nil,"a saved job is not in the older journal before lp")
    printer!.process("one");_=try printer!.printJob(body("one"));try check(submissions==1,"one submission")
    // WMS-625: the older program started again finds the key with the same hash and receipt.
    try check(try olderJournal(root)["one"]==LegacyEntry(hash:try printer!.detail("one")!["hash"] as! String,receipt:"test-printer-1",v2:true),"accepted job mirrored for the older program")
    // The decoder of v2026.09.30.4 (hash, optional receipt) reads the mirrored file as is.
    struct Release4Entry: Codable { let hash:String; var receipt:String? }
    let release4=try JSONDecoder().decode([String:Release4Entry].self,from:Data(contentsOf:root.appendingPathComponent("direct-jobs.json")))
    try check(release4["one"]?.receipt=="test-printer-1","v2026.09.30.4 decodes the mirrored journal")
    _=try printer!.reconcile("one");try check(try printer!.detail("one")?["status"] as? String == "completed","observed completed")
    try check(try printer!.detail("one")?["paperStatus"] as? String == "unconfirmed","paper distinct")
    var changed=body("one");changed["widthMm"]=60
    do{_=try printer!.printJob(changed);throw PrintError.message("Expected changed size rejection")}catch PrintError.message(let message){try check(message.contains("изменились"),"size conflict")}
    for i in 0..<350 {_=try printer!.printJob(body("batch-\(i)"))}
    try check((try printer!.list()["jobs"] as! [[String:Any]]).count==351,"350 saved jobs")
    printer=nil
    printer=try Printer(directory:root,autoWork:false,submit:{_,_ in throw PrintError.message("lost OS response")},queue:{"test-printer"},observe:{_ in ["matches":1,"receipt":"test-printer-999","jobState":5]})
    try check(try printer!.image("one")==png,"image survives restart")
    printer!.process("batch-0");try check(try printer!.detail("batch-0")?["status"] as? String == "unknown","unknown preserved")
    try check(try olderJournal(root)["batch-0"]?.receipt==nil && olderJournal(root)["batch-0"] != nil,"unknown outcome mirrored as begun: the older program refuses a repeat")
    _=try printer!.printJob(body("batch-0"));_=try printer!.reconcile("batch-0")
    try check(try printer!.detail("batch-0")?["receipt"] as? String == "test-printer-999","lost receipt reconciles")
    try check(try olderJournal(root)["batch-0"]?.receipt=="test-printer-999","reconciled receipt mirrored")
    printer=nil
    printer=try Printer(directory:root,autoWork:false,submit:{_,_ in throw PrintError.beforeSubmit("launch failed")},queue:{"test-printer"})
    printer!.process("batch-1");try check(try printer!.detail("batch-1")?["status"] as? String == "failed_before_submit","known pre-submit failure")
    try check(try olderJournal(root)["batch-1"]==nil,"a proven unsent job is not left in the older journal")
    _=try printer!.retry("batch-1");try check(try printer!.detail("batch-1")?["status"] as? String == "saved","safe explicit retry")
    try check(parseReceipt("id запроса Test_Printer-42 (файлов 1)",queue:"Test_Printer")=="Test_Printer-42","localized receipt")
    try check(parseReceipt("other-Test_Printer-42",queue:"Test_Printer")==nil,"receipt boundaries")
    let result=try run("/bin/sh",["-c","trap '' TERM; yes x | head -c 200000; sleep 5"],timeout:0.1)
    try check(result.timedOut,"process timeout bounded despite output and ignored TERM")
    printer=nil
    // A process exit is stronger evidence than re-instantiating an in-memory store.
    for phase in ["saved","submitted"] {
        let path=root.appendingPathComponent("crash-"+phase)
        let result=try run(URL(fileURLWithPath:CommandLine.arguments[0]).standardizedFileURL.path,["--self-test-child",path.path,phase],timeout:10)
        try check(result.status == (phase=="saved" ? 70:71),"child abrupt exit")
        var calls=0
        let recovered=try Printer(directory:path,autoWork:false,submit:{_,_ in calls+=1;return "test-printer-92"},queue:{"test-printer"},observe:{_ in ["matches":1,"receipt":"test-printer-91","jobState":5]})
        try check(try recovered.image("crash")==png,"crash exact PNG")
        try check(try recovered.detail("crash")?["status"] as? String == (phase=="saved" ? "saved":"unknown"),"crash boundary state")
        if phase=="submitted" {
            _=try recovered.reconcile("crash");_=try recovered.printJob(body("crash"));try check(calls==0,"crash no second OS call")
            try check(try recovered.detail("crash")?["receipt"] as? String == "test-printer-91","crash receipt recovered")
        } else { recovered.process("crash");try check(calls==1,"saved resumes") }
    }
    for failingWrite in [1,2,3,4] {
        var writes=0;var calls=0
        let path=root.appendingPathComponent("write-\(failingWrite)")
        var subject:Printer?=try Printer(directory:path,autoWork:false,submit:{_,_ in calls+=1;return "test-printer-1"},queue:{"test-printer"},write:{data,url in
            writes+=1
            if writes==failingWrite { throw PrintError.message("injected disk failure") }
            try durableWrite(data,url)
        })
        if failingWrite<=2 {
            do { _=try subject!.printJob(body("disk"));throw PrintError.message("expected disk failure") } catch {}
            try check(try subject!.detail("disk")==nil,"failed enqueue never poisons memory")
            _=try subject!.printJob(body("disk"));subject!.process("disk");try check(calls==1,"same key retry after disk repair")
        } else {
            _=try subject!.printJob(body("disk"));subject!.process("disk")
            try check(calls==(failingWrite==3 ? 0:1),"storage boundary protects external call")
            subject=nil
            let recovered=try Printer(directory:path,autoWork:false,queue:{throw PrintError.beforeSubmit("no default")})
            try check(try recovered.detail("disk")?["status"] as? String == (failingWrite==3 ? "failed_before_submit":"unknown"),"failed result never blind retries")
        }
    }
    // Exercise the narrow retry-vs-worker-release race deterministically.
    let failed=DispatchSemaphore(value:0), release=DispatchSemaphore(value:0)
    var raceCalls=0
    let race=try Printer(directory:root.appendingPathComponent("race"),submit:{_,_ in
        raceCalls+=1
        if raceCalls==1 { throw PrintError.beforeSubmit("launch failed") }
        return "test-printer-2"
    },queue:{"test-printer"},beforeRelease:{ if raceCalls==1 { failed.signal();_=release.wait(timeout:.now()+2) } })
    _=try race.printJob(body("race"));try check(failed.wait(timeout:.now()+2) == .success,"race first failure")
    _=try race.retry("race");release.signal()
    let deadline=Date().addingTimeInterval(3)
    while try race.detail("race")?["status"] as? String != "accepted" && Date()<deadline { Thread.sleep(forTimeInterval:0.01) }
    try check(try race.detail("race")?["status"] as? String == "accepted","retry is rescheduled after active worker release")
    // Linked explicit copies survive restart without rewriting the original outcome.
    let linkedPath=root.appendingPathComponent("linked")
    var linked:Printer?=try Printer(directory:linkedPath,autoWork:false,submit:{_,_ in "test-printer-7"},queue:{"test-printer"},observe:{_ in ["matches":1,"receipt":"test-printer-7","jobState":7]})
    _=try linked!.printJob(body("parent"));linked!.process("parent");_=try linked!.reconcile("parent")
    let childBody:[String:Any] = ["idempotencyKey":"child","acknowledgeDuplicateRisk":true]
    _=try linked!.reprint("parent",body:childBody);linked!.process("child");_=try linked!.reprint("parent",body:childBody)
    linked=nil
    linked=try Printer(directory:linkedPath,autoWork:false)
    let parent=try linked!.detail("parent")!;let children=parent["reprints"] as! [[String:Any]]
    try check(parent["status"] as? String == "canceled" && children.count==1,"linked copy does not erase parent cancellation")
    try check(children[0]["hash"] as? String == parent["hash"] as? String && children[0]["receipt"] as? String == "test-printer-7","linked copy exact content and receipt")
    try check((children[0]["context"] as? [String:Any])?["wbOrderId"] as? Int == 456,"numeric order context preserved")
    // Malformed optional dimensions are a diagnostic, not a fatal force-unwrap.
    linked=nil
    let childFile=linkedPath.appendingPathComponent("jobs-v2/"+digest(Data("child".utf8))+".json")
    var malformed=try JSONSerialization.jsonObject(with:Data(contentsOf:childFile)) as! [String:Any]
    malformed.removeValue(forKey:"widthMm")
    try durableWrite(JSONSerialization.data(withJSONObject:malformed),childFile)
    linked=try Printer(directory:linkedPath,autoWork:false)
    try check((try linked!.list()["jobs"] as! [[String:Any]]).count==1,"corrupt child does not hide other history")
    try check(!(try linked!.list()["diagnostics"] as! [String]).isEmpty,"corrupt child diagnostic")
    linked=nil
    try FileManager.default.removeItem(at:childFile)
    linked=try Printer(directory:linkedPath,autoWork:false)
    do { _=try linked!.printJob(body("child"));throw PrintError.message("orphan PNG accepted") }
    catch PrintError.message(let message) { try check(message.contains("повреждена"),"orphan PNG cannot cause duplicate after restart") }
    // WMS-625: if the older journal cannot be written, the job does not reach lp.
    var mirrorCalls=0
    let mirrorFails=try Printer(directory:root.appendingPathComponent("older-unwritable"),autoWork:false,submit:{_,_ in mirrorCalls+=1;return "test-printer-6"},queue:{"test-printer"},legacyWrite:{_,_ in throw PrintError.message("read-only older journal")})
    _=try mirrorFails.printJob(body("mirror"));mirrorFails.process("mirror")
    try check(mirrorCalls==0 && (try mirrorFails.detail("mirror")?["status"] as? String)=="failed_before_submit","older journal is written before lp or nothing is submitted")
    // WMS-625: the older program ran between two runs of this one and printed a job this
    // one had only saved: its receipt completes the job, nothing goes to the queue again.
    let olderRanPath=root.appendingPathComponent("older-ran")
    var olderRanCalls=0
    var olderRan:Printer?=try Printer(directory:olderRanPath,autoWork:false,submit:{_,_ in olderRanCalls+=1;return "test-printer-5"},queue:{"test-printer"})
    let printedHash=try olderRan!.printJob(body("older-printed"))["hash"] as! String
    let begunHash=try olderRan!.printJob(body("older-begun"))["hash"] as! String
    olderRan=nil
    // Exactly what v2026.09.30.4 writes: its StoredJob has no v2 field.
    try durableWrite(JSONEncoder().encode(["older-printed":LegacyEntry(hash:printedHash,receipt:"old-7"),"older-begun":LegacyEntry(hash:begunHash,receipt:nil)]),olderRanPath.appendingPathComponent("direct-jobs.json"))
    olderRan=try Printer(directory:olderRanPath,autoWork:false,submit:{_,_ in olderRanCalls+=1;return "test-printer-5"},queue:{"test-printer"})
    olderRan!.process("older-printed");olderRan!.process("older-begun")
    try check(olderRanCalls==0,"jobs the older program took are never submitted again")
    try check(try olderRan!.detail("older-printed")?["status"] as? String == "accepted" && olderRan!.detail("older-printed")?["receipt"] as? String == "old-7","older receipt completes the saved job")
    try check(try olderRan!.detail("older-begun")?["status"] as? String == "unknown","older unfinished attempt is unknown, not resent")
    olderRan=nil
    let legacyPath=root.appendingPathComponent("legacy")
    try FileManager.default.createDirectory(at:legacyPath,withIntermediateDirectories:true)
    var identity=png;identity.append(Data("|58.0x40.0".utf8))
    let oldData=try JSONSerialization.data(withJSONObject:["v3":["hash":digest(png),"receipt":"test-printer-3"],"v4":["hash":digest(identity),"receipt":"test-printer-4"],"uncertain":["hash":digest(identity)]])
    let oldFile=legacyPath.appendingPathComponent("direct-jobs.json")
    try durableWrite(oldData,oldFile)
    let old=try Printer(directory:legacyPath,autoWork:false,submit:{_,_ in throw PrintError.message("legacy must not submit")})
    for key in ["v3","v4","uncertain"] {
        let job=try old.printJob(body(key))
        try check(job["legacy"] as? Bool == true && job["imageAvailable"] as? Bool == false && job["widthMm"]==nil,"legacy provenance preserved")
    }
    try check(try Data(contentsOf:oldFile)==oldData,"old journal untouched")
    let missingPath=root.appendingPathComponent("missing-child")
    var available=false
    var missing:Printer?=try Printer(directory:missingPath,autoWork:false,submit:{_,_ in "test-printer-8"},queue:{if !available { throw PrintError.beforeSubmit("no printer") };return "test-printer"})
    _=try missing!.printJob(body("source"));missing!.process("source");available=true
    let missingBody:[String:Any] = ["idempotencyKey":"lost-child","acknowledgeDuplicateRisk":true]
    _=try missing!.reprint("source",body:missingBody);missing!.process("lost-child");missing=nil
    for ext in ["json","png"] { try FileManager.default.removeItem(at:missingPath.appendingPathComponent("jobs-v2/"+digest(Data("lost-child".utf8))+"."+ext)) }
    missing=try Printer(directory:missingPath,autoWork:false)
    let unknownChildren=try missing!.detail("source")!["reprints"] as! [[String:Any]]
    try check(unknownChildren.count==1 && unknownChildren[0]["status"] as? String == "unknown" && unknownChildren[0]["receipt"]==nil,"missing linked record stays unknown")
    do { _=try missing!.retry("source");throw PrintError.message("parent repeated") } catch PrintError.message(let message) {try check(message.contains("неизвестен"),"parent retry blocked by durable child intent")}
    do { _=try missing!.reprint("source",body:missingBody);throw PrintError.message("child repeated") } catch PrintError.message(let message) {try check(message.contains("утрачено"),"same lost child cannot be recreated")}
    do { _=try missing!.printJob(body("lost-child"));throw PrintError.message("child repeated through print") } catch PrintError.message(let message) {try check(message.contains("утрачено"),"plain print cannot recreate lost child")}
    let observationEntered=DispatchSemaphore(value:0),observationRelease=DispatchSemaphore(value:0),observationDone=DispatchSemaphore(value:0)
    let stale=try Printer(directory:root.appendingPathComponent("stale-observe"),autoWork:false,submit:{_,_ in "test-printer-9"},queue:{"test-printer"},observe:{_ in
        observationEntered.signal();_=observationRelease.wait(timeout:.now()+3)
        return ["matches":1,"receipt":"test-printer-9","jobState":7]
    })
    _=try stale.printJob(body("source"));stale.process("source")
    DispatchQueue.global().async { _=try? stale.reconcile("source");observationDone.signal() }
    try check(observationEntered.wait(timeout:.now()+1) == .success,"observer entered")
    _=try stale.reprint("source",body:["idempotencyKey":"stale-child","acknowledgeDuplicateRisk":true])
    observationRelease.signal();try check(observationDone.wait(timeout:.now()+1) == .success,"observer finished")
    try check(try stale.detail("source")?["reprintIntentKeys"] as? [String] == ["stale-child"],"stale observer cannot erase link even within same timestamp second")
    print("WMS Print Direct macOS: package OK; durable 350 jobs, abrupt process exits, disk faults, lost receipt, reconciliation, explicit copies, retry race, dimensions, process timeout")
}
private func runServer(testDirectory:URL?=nil) throws {
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
    let printer:Printer
    if let directory=testDirectory {
        var count=0
        printer=try Printer(directory:directory,submit:{_,_ in
            count+=1;try durableWrite(Data(String(count).utf8),directory.appendingPathComponent("submission-count"));return "test-printer-\(count)"
        },queue:{"test-printer"},observe:{job in
            let file=directory.appendingPathComponent("observation.json")
            if FileManager.default.fileExists(atPath:file.path) { return try JSONSerialization.jsonObject(with:Data(contentsOf:file)) as! [String:Any] }
            return ["matches":1,"receipt":job.receipt ?? "test-printer-1","jobState":5]
        })
    } else { printer=try Printer(directory:appSupport.appendingPathComponent("WMS Print/direct")) }
    printer.poll()
    print("WMS Print запущена. История и восстановление: \(localOrigin). Оставьте это окно открытым.")
    fflush(stdout)
    while true {
        let client = Darwin.accept(descriptor, nil, nil)
        if client >= 0 { DispatchQueue.global(qos: .userInitiated).async { handle(client, printer: printer) } }
    }
}

do {
    if CommandLine.arguments.count == 3 && CommandLine.arguments[1] == "--self-test-http" {
        try runServer(testDirectory:URL(fileURLWithPath:CommandLine.arguments[2]))
    } else if CommandLine.arguments.count == 4 && CommandLine.arguments[1] == "--self-test-child" {
        try runCrashFixture(CommandLine.arguments[2],CommandLine.arguments[3])
    } else if CommandLine.arguments.count == 5 && CommandLine.arguments[1] == "--observe" {
        _ = cupsObserve(CommandLine.arguments[2],CommandLine.arguments[3],CommandLine.arguments[4])
    } else if CommandLine.arguments.contains("--self-test") { try runSelfTest() } else { try runServer() }
} catch {
    fputs("\(String(describing: error))\n", stderr)
    exit(1)
}
