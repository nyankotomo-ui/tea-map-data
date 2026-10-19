# tea-map-data

「Tea Map」アプリが読み込む、紅茶専門店の公開データです。/ Public release data read by the Tea Map app.

## ファイル / Files

| ファイル | 内容 |
|---|---|
| `shops.release.json` | 店舗データ本体（現在 97 件） |
| `release.meta.json` | バージョン情報（`data_version`、`generated_at`、`shop_count` など） |
| `SHA256SUMS.txt` | 上の 2 ファイルの SHA-256 |

アプリは `release.meta.json` を先に読み、新しい版のときだけ `shops.release.json` を取得します。

## 注意 / Notes

- 位置情報は近似です。店舗の正確な位置として扱わないでください（`release.meta.json` の `coordinate_policy` を参照）。
- 住所・URL・営業状況は変わることがあります。お出かけ前に店舗の公式情報をご確認ください。
- このリポジトリのファイルは自動生成物です。手で編集しないでください。内容の変更は生成元で行います。
- ライセンスは未定です（決まり次第ここに記載します）。

This repository holds generated files only; please do not edit them by hand.
Coordinates are approximate. License: to be announced.
