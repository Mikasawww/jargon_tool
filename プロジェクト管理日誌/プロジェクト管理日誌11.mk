# プロジェクト管理日誌 Day 11

## 記録日：2026年10月14日

### 1. 本日完了した機能

- PyInstaller による exe パッケージング（onedir 形式・コンソールなし、約900MB）
- 外置 .env による API Key 管理（exe 同階層に初回自動生成、再パッケージ不要）
- リソースパス適配（`resource_path()`：開発時＝プロジェクト、パッケージ後＝sys._MEIPASS）
- embedding シードキャッシュ同梱（初回起動時にユーザー領域へコピー、再計算不要）
- 不要ファイル整理（setup_rag_env.bat、旧 kb_embeddings_ja.npz を削除）
- exe 起動検証：起動・ログ・.env生成・キャッシュシードをすべて確認

### 2. 遭遇した問題

- **exe が起動直後にクラッシュ（ログすら残らない）**
  - 原因：外置 .env テンプレートの `DEEPSEEK_API_KEY=` が空の状態で、
    analyze.py が import 時に `OpenAI(api_key="")` を実行
  - openai 3.x は空 Key で即座に例外を送出するため、logger 初期化前にプロセスが終了
  - 開発環境では .env に実 Key があり、本問題が顕在化していなかった
- .env をパッケージに含めると実 Key が漏洩するリスク
- モデル（約420MB）同梱すると exe が巨大化する問題

### 3. 分析と解決方法

- **空 Key クラッシュ**：クライアント生成を遅延初期化 `_get_client()` に変更。
  Key 未設定時は import 時に例外を出さず、分析実行時に新規例外
  `APIKeyMissingError`（E009）を送出。3言語ロケールに
  「.env を編集して再起動」旨のエラーメッセージを追加
- **Key 漏洩防止**：.env は datas に含めず、main.py で
  「存在しなければテンプレート生成」方式に変更
- **モデル巨大化**：モデルは同梱せず、初回起動時に hf-mirror.com から
  ユーザーキャッシュへダウンロード。2回目以降はローカル読み込みのみ
- **初回コスト最小化**：embedding ベクトル（85件・npz 約数MB）は
  シードとして同梱し、初回起動時にユーザー領域へコピー。
  モデルさえローカルにあれば再計算・再ダウンロードは一切不要
- **リソースパス**：config.py に `resource_path()` を新設し、
  知識庫・locales・シードキャッシュの参照を一元化。
  DB・ログ・embedding キャッシュは従来どおり `~/.biz_jargon_tool/`（可写）

### 4. 使用した技術方案

- PyInstaller 6.x：`.spec` ファイルで onedir / windowed（console=False）構成
- `collect_submodules`：sentence_transformers / transformers / fugashi /
  unidic_lite / sklearn / scipy の動的インポートを網羅
- `collect_data_files`：unidic_lite 辞書・fugashi データの同梱
- `excludes`：matplotlib / pandas / PyQt 等の未使用重パッケージを除外
- `sys.frozen` / `sys._MEIPASS` による実行形態判定
- python-dotenv による外置 .env 読込（`load_dotenv(ENV_FILE)`）
- shutil.copy2 によるシードキャッシュの初回コピー

### 5. 関連する日本語技術用語

| 日本語 | 読み | 中文 | 英語 |
|--------|------|------|------|
| パッケージング | パッケージング | 打包 | Packaging |
| 実行ファイル | じっこうファイル | 可执行文件 | Executable |
| 同梱 | どうこん | 随包附带 | Bundling |
| 遅延初期化 | ちえんしょきか | 延迟初始化 | Lazy initialization |
| シード | シード | 种子（预置数据） | Seed |
| リソースパス | リソースパス | 资源路径 | Resource path |
| キー漏洩 | キーろうえい | 密钥泄露 | Key leakage |
| 起動検証 | きどうけんしょう | 启动验证 | Launch verification |

---
