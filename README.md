# LLM Trans

macOS向けリアルタイム字幕・翻訳アプリ。ブラウザや動画プレイヤーの音声をキャプチャし、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)で文字起こし、[Ollama](https://ollama.com/)でリアルタイム翻訳して字幕表示します。

## 特徴

- **アプリ別音声キャプチャ** — ScreenCaptureKitで特定アプリの音声だけを取得（システム全体の音声キャプチャにも対応）
- **並列文字起こし** — 2ワーカーが50%オーバーラップで処理し、途切れない字幕を実現
- **リアルタイム翻訳** — OllamaのローカルLLMで翻訳（translategemma等に対応）
- **字幕オーバーレイ** — 常に最前面に表示、ドラッグ移動・フォントサイズ変更可能
- **短文/リストモード** — 最新数行の短文表示と、タイムスタンプ付きスクロールログの切替
- **設定の永続化** — 前回の設定を自動保存・復元

## 対応環境

- **OS:** macOS 14 (Sonoma) 以降
- **CPU:** Apple Silicon (M1/M2/M3/M4) 推奨
- **Python:** 3.11以降
- **Ollama:** 翻訳機能を使う場合のみ必要

## セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/your-username/llmtrans.git
cd llmtrans
```

### 2. Python環境の構築

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. ScreenCaptureKitヘルパーのビルド

アプリ別音声キャプチャを使うには、Swiftヘルパーをビルドします:

```bash
cd audio
swiftc capture_helper.swift -o capture_helper -framework ScreenCaptureKit -framework CoreMedia -framework AVFoundation
cd ..
```

> ビルドにはXcode Command Line Toolsが必要です: `xcode-select --install`

### 4. Ollama（翻訳機能を使う場合）

```bash
# Ollamaのインストール（未導入の場合）
brew install ollama

# 翻訳モデルのダウンロード
ollama pull translategemma:4b
```

## 使い方

### 起動

```bash
./run.sh
```

または:

```bash
source venv/bin/activate
python main.py
```

### 操作手順

1. **音声キャプチャ方式を選択** — ScreenCaptureKit（アプリ別）またはBlackHole（システム音声）
2. **対象アプリを選択** — ScreenCaptureKit使用時は、キャプチャしたいアプリを一覧から選択
3. **Whisperモデル・言語を設定** — モデルサイズと音声の言語を選択
4. **翻訳を設定（任意）** — 「翻訳を有効にする」にチェック → 翻訳元/先の言語を選択
5. **「開始」をクリック** — 初回はモデルダウンロードに時間がかかります

### 字幕オーバーレイの操作

- **ドラッグ** — 字幕ウィンドウをドラッグで移動
- **マウスホイール** — フォントサイズの変更
- **右クリック** — 表示モード切替（短文/リスト）、フォントサイズ変更

## 音声キャプチャ方式

### ScreenCaptureKit（推奨）

特定アプリの音声だけをキャプチャします。初回起動時にmacOSの「画面収録」権限の許可が必要です。

### BlackHole

[BlackHole](https://github.com/ExistentialAudio/BlackHole)仮想オーディオデバイス経由でシステム全体の音声をキャプチャします。別途BlackHoleのインストールとmacOSのオーディオ設定が必要です。

## ライセンス

[MIT License](LICENSE)
