# EventStorming サンプル

イベントフローの描画確認用フィクスチャ。

## 3) Event Walkthrough

### ハッピーパス

```event-flow-svg
title: ハッピーパス
flow:
|community|: 主催者がコミュニティを起点に活動を始める
  @主催者 > !コミュニティを作成 > [コミュニティが作成された] >>
|registration|: イベント公開を受けて参加者の申込フローへ
  @参加者 > ?残席数 > !参加を申し込む > [参加が申し込まれた]
```

### 中止 Saga（BULK 並列返金 → Join）

```event-flow-svg
title: イベント中止 Saga
flow:
|event-planning|: 主催者起点の中止要求
  @主催者 > !イベント中止を要求 > [イベント中止が要求された] >>
|ticketing|: 全 confirmed 申込を BULK 並列返金
  $中止時の一括返金 *> !返金を実行 > [返金が完了した] &>>
|event-planning|: 全 N 件の返金完了 Join で中止確定
  $全返金完了時の中止確定 > !イベント中止を確定 > [イベント中止が確定した]
```

## 4) その後

通常の Markdown 段落はそのまま表示される。
