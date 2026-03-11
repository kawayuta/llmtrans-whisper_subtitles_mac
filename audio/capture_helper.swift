// ScreenCaptureKit を使って特定アプリの音声をキャプチャし、
// 標準出力にraw PCM float32 mono 16kHzで出力するヘルパー。
// Usage: capture_helper <PID>
// Usage: capture_helper --list  (実行中アプリ一覧を出力)

import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia

// MARK: - App Listing

func listApps() async {
    do {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        for app in content.applications {
            let pid = app.processID
            let name = app.applicationName
            let bundleID = app.bundleIdentifier
            // JSON Lines形式で出力
            print("{\"pid\":\(pid),\"name\":\"\(name)\",\"bundle_id\":\"\(bundleID)\"}")
        }
    } catch {
        FileHandle.standardError.write("Error listing apps: \(error)\n".data(using: .utf8)!)
    }
}

// MARK: - Audio Capture

class AudioCaptureDelegate: NSObject, SCStreamDelegate, SCStreamOutput {
    let targetSampleRate: Double = 16000
    var converter: AVAudioConverter?
    var inputFormat: AVAudioFormat?
    let outputFormat: AVAudioFormat

    override init() {
        self.outputFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: 16000,
            channels: 1,
            interleaved: true
        )!
        super.init()
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio else { return }
        guard let formatDesc = sampleBuffer.formatDescription else { return }

        let audioStreamBasicDescription = CMAudioFormatDescriptionGetStreamBasicDescription(formatDesc)
        guard let asbd = audioStreamBasicDescription?.pointee else { return }

        // 初回: コンバーター設定
        if converter == nil {
            inputFormat = AVAudioFormat(
                commonFormat: .pcmFormatFloat32,
                sampleRate: asbd.mSampleRate,
                channels: AVAudioChannelCount(asbd.mChannelsPerFrame),
                interleaved: false
            )
            if let inputFormat = inputFormat {
                converter = AVAudioConverter(from: inputFormat, to: outputFormat)
            }
        }

        // CMSampleBuffer → PCMBuffer
        guard let blockBuffer = CMSampleBufferGetDataBuffer(sampleBuffer) else { return }
        let numSamples = CMSampleBufferGetNumSamples(sampleBuffer)
        guard numSamples > 0 else { return }

        var length: Int = 0
        var dataPointer: UnsafeMutablePointer<Int8>?
        CMBlockBufferGetDataPointer(blockBuffer, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length, dataPointerOut: &dataPointer)
        guard let dataPointer = dataPointer else { return }

        guard let inputFormat = inputFormat else { return }
        let channelCount = Int(inputFormat.channelCount)
        let frameCount = AVAudioFrameCount(numSamples)

        guard let inputBuffer = AVAudioPCMBuffer(pcmFormat: inputFormat, frameCapacity: frameCount) else { return }
        inputBuffer.frameLength = frameCount

        // データをコピー
        let floatData = UnsafeRawPointer(dataPointer).bindMemory(to: Float.self, capacity: numSamples * channelCount)
        if inputFormat.isInterleaved {
            if let dest = inputBuffer.floatChannelData?[0] {
                dest.update(from: floatData, count: numSamples * channelCount)
            }
        } else {
            for ch in 0..<channelCount {
                if let dest = inputBuffer.floatChannelData?[ch] {
                    for i in 0..<numSamples {
                        dest[i] = floatData[i * channelCount + ch]
                    }
                }
            }
        }

        // リサンプル + モノラル変換
        guard let converter = converter else { return }
        let ratio = outputFormat.sampleRate / inputFormat.sampleRate
        let outputFrameCount = AVAudioFrameCount(Double(frameCount) * ratio)
        guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: outputFrameCount + 1) else { return }

        var error: NSError?
        var consumed = false
        converter.convert(to: outputBuffer, error: &error) { _, outStatus in
            if consumed {
                outStatus.pointee = .noDataNow
                return nil
            }
            consumed = true
            outStatus.pointee = .haveData
            return inputBuffer
        }

        if let error = error {
            FileHandle.standardError.write("Convert error: \(error)\n".data(using: .utf8)!)
            return
        }

        // 標準出力に書き出し
        let count = Int(outputBuffer.frameLength)
        if count > 0, let channelData = outputBuffer.floatChannelData?[0] {
            let data = Data(bytes: channelData, count: count * MemoryLayout<Float>.size)
            FileHandle.standardOutput.write(data)
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        FileHandle.standardError.write("Stream stopped: \(error)\n".data(using: .utf8)!)
        exit(1)
    }
}

func captureAudio(pid: Int32) async {
    do {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)

        guard let targetApp = content.applications.first(where: { $0.processID == pid }) else {
            FileHandle.standardError.write("App with PID \(pid) not found\n".data(using: .utf8)!)
            exit(1)
        }

        guard let display = content.displays.first else {
            FileHandle.standardError.write("No display found\n".data(using: .utf8)!)
            exit(1)
        }

        FileHandle.standardError.write("Capturing audio from: \(targetApp.applicationName) (PID: \(pid))\n".data(using: .utf8)!)

        let filter = SCContentFilter(display: display, including: [targetApp], exceptingWindows: [])

        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = 48000
        config.channelCount = 2
        // 映像は最小化
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1) // 1fps

        let delegate = AudioCaptureDelegate()
        let stream = SCStream(filter: filter, configuration: config, delegate: delegate)

        try stream.addStreamOutput(delegate, type: .audio, sampleHandlerQueue: DispatchQueue(label: "audio"))

        try await stream.startCapture()
        FileHandle.standardError.write("READY\n".data(using: .utf8)!)

        // SIGINTハンドリング
        signal(SIGINT) { _ in
            exit(0)
        }
        signal(SIGTERM) { _ in
            exit(0)
        }

        // 無限待機
        await withCheckedContinuation { (_: CheckedContinuation<Void, Never>) in
            // Never resumes - runs until killed
        }

    } catch {
        FileHandle.standardError.write("Capture error: \(error)\n".data(using: .utf8)!)
        exit(1)
    }
}

// MARK: - Main

let args = CommandLine.arguments

if args.count < 2 {
    FileHandle.standardError.write("Usage: capture_helper <PID> | --list\n".data(using: .utf8)!)
    exit(1)
}

if args[1] == "--list" {
    Task {
        await listApps()
        exit(0)
    }
    RunLoop.main.run()
} else if let pid = Int32(args[1]) {
    Task {
        await captureAudio(pid: pid)
    }
    RunLoop.main.run()
} else {
    FileHandle.standardError.write("Invalid argument: \(args[1])\n".data(using: .utf8)!)
    exit(1)
}
