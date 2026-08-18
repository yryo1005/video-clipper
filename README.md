# Video Clipper

YouTube から動画を取り込み、範囲指定してクリップを書き出す Windows 用アプリです。
元の単一ファイルプロトタイプ (`VideoClipper.py`) と同じ操作感を保ちつつ、UI / 再生 / ダウンロード / 書き出しを分けています。

## 必要なもの

- Python 3.11 以上
- [ffmpeg](https://ffmpeg.org/)（PATH に通す）
- [Deno](https://deno.com/)（YouTube ダウンロード用。未導入なら winget で `DenoLand.Deno`）

## 起動

デスクトップの `VideoClipper.bat`、またはプロジェクト直下の同じファイルをダブルクリックします。

初回だけ仮想環境の作成とパッケージ導入が走ります。

手動で起動する場合:

```bat
cd /d C:\Users\Ryo\workspace\video-clipper
.venv\Scripts\python.exe -m videoclipper
```

## 操作

- **Open**: ローカル動画を開く
- **Download**: YouTube URL を保存して読み込む
- 緑 / 赤スライダー: Start / End。右クリックで現在位置に合わせる
- End 指定時は 2 秒前からプレビュー
- スペース / 映像クリック: 再生・一時停止
- **EXPORT**: `Videos\MyClips` にクリップ保存
- History: 書き出したクリップ。右クリックで削除

クリップ出力先は従来どおり `%USERPROFILE%\Videos\MyClips` です。
YouTube の取り込み先は `%USERPROFILE%\Videos\VideoClipper\downloads` です。
音量は `%APPDATA%\VideoClipper\settings.json` に保存します。
