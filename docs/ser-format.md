# SER フォーマット覚書

SER Viewer が実装している SER v3 の解釈をまとめたものです。実装は
`serview/ser/format.py` と `serview/ser/reader.py` にあります。

## ファイル全体

```
+--------------------+  0
| ヘッダ 178 バイト    |
+--------------------+  178
| フレームデータ        |  FrameCount 個、パディングなし
+--------------------+  178 + FrameCount * FrameSize
| タイムスタンプ（任意） |  8 バイト * FrameCount
+--------------------+
```

`FrameSize = ImageWidth * ImageHeight * planes * bytesPerSample`

- `planes` は ColorID が RGB / BGR のとき 3、それ以外は 1
- `bytesPerSample` は `PixelDepthPerPlane <= 8` なら 1、9〜16 なら 2

## ヘッダ（178 バイト、すべてリトルエンディアン）

| オフセット | 型 | フィールド | 備考 |
|---|---|---|---|
| 0 | char[14] | FileID | 通常 `LUCAM-RECORDER` |
| 14 | int32 | LuID | 未使用（0） |
| 18 | int32 | ColorID | 下表 |
| 22 | int32 | LittleEndian | **0 = リトル、1 = ビッグ**（仕様の名前と逆） |
| 26 | int32 | ImageWidth | |
| 30 | int32 | ImageHeight | |
| 34 | int32 | PixelDepthPerPlane | 1〜16 |
| 38 | int32 | FrameCount | |
| 42 | char[40] | Observer | UTF-8、NUL 埋め |
| 82 | char[40] | Instrument | |
| 122 | char[40] | Telescope | |
| 162 | int64 | DateTime | 現地時刻 |
| 170 | int64 | DateTime_UTC | UTC |

### ColorID

| 値 | 意味 |
|---|---|
| 0 | MONO |
| 8 / 9 / 10 / 11 | ベイヤー RGGB / GRBG / GBRG / BGGR |
| 16 / 17 / 18 / 19 | ベイヤー CYYM / YCMY / YMCY / MYYC |
| 100 | RGB（画素ごとに R,G,B の順） |
| 101 | BGR |

### 時刻の表現

いずれも **0001-01-01 00:00:00 からの 100 ns 単位**の 64 bit 整数
（.NET の `DateTime.Ticks` と同じ）。0 は「未設定」を意味します。

## 実装上の注意点

SER Viewer は以下の“現実のファイル”への対処を入れています。

1. **`LittleEndian` の反転**
   仕様上 `1` が **ビッグ**エンディアンを意味します（SER Player も同じ扱い）。

2. **タイムスタンプが UTC でないことがある**
   一部の録画ソフトは末尾のタイムスタンプに現地時刻を書きます。ヘッダの
   `DateTime` と `DateTime_UTC` のどちらが末尾の最小値に近いかで判定し、
   現地時刻だった場合はオフセットを足して UTC に揃えます。

3. **`PixelDepthPerPlane` があてにならない**
   10 / 12 / 14 bit のカメラでも 16 と書くソフトが多く、そのまま表示すると
   極端に暗くなります。先頭・中間・末尾の 10 フレームを走査して全画素の OR を
   取り、立っている最上位ビットから実効深度を求めます（SER Player と同じ手法）。
   測定値は表示のスケーリングと FITS の `SERDEPTH` に使われ、
   **画素値そのものは書き換えません**。

4. **フレーム数が実ファイルより多い**
   録画が中断されたファイルではよくあります。読める範囲に切り詰めて警告します。

## 参考

- SER format description v3 — Heiko Wilkens, Grischa Hahn
- [SER Player](https://github.com/cgarry/ser-player) — Chris Garry（GPL-3.0）
