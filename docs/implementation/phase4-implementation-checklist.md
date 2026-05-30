# Phase 4 実装チェックリスト（Label Generation）

## 実装項目
- [ ] TP/SL先着2値ラベル生成を実装
- [ ] `max_horizon_bars` 探索上限を実装
- [ ] timestamp整合チェック（単調増加・重複禁止）を実装
- [ ] leakage検証（featuresとのtimestamp一致）を実装
- [ ] Label Parquet保存を実装
- [ ] CLI実行導線を実装

## Done定義
- [ ] `label in {0,1,null}` の契約を満たす
- [ ] duplicate / 非単調timestamp入力でfail-fastする
- [ ] leakage不一致時にジョブ失敗する
- [ ] ユニット/パイプラインテストが通る

## レビュー観点
1. `future_return` 回帰を導入していないこと
2. 未来参照はラベル生成に限定され、特徴量側へ混入しないこと
3. 同一timestampキーでfeaturesと結合できること
