# Point-review V1

基于 `设计文档.md` 的本地单用户版本。支持 Point 管理、Markdown 批量导入、AI 语境四选一、复习调度、熟练度结算和复习结果。数据保存在本机 SQLite 数据库。只需 Python 3.10 或更新版本，不需要安装第三方包。

## 启动

在项目目录执行：

```bash
export OPENAI_API_KEY="你的 API Key"
export OPENAI_MODEL="支持 JSON 输出的模型名"
python3 -m app.server
```

打开 <http://127.0.0.1:8000>。

默认调用 `https://api.openai.com/v1/chat/completions`。如果使用兼容 Chat Completions 的服务，可设置 `OPENAI_BASE_URL` 为其 `/v1` 基础地址。也可设置 `POINT_REVIEW_PORT`、`POINT_REVIEW_HOST` 和 `POINT_REVIEW_TIMEZONE`（默认 `Asia/Shanghai`）。密钥仅由后端读取，不会返回给浏览器。未配置 AI 时，Point 管理和导入仍可使用，复习入口会显示配置提示。

## Markdown 格式

```markdown
- perspective
  - n. 观点，看法，视角
    - from a different perspective = 从不同角度看
  - keep sth in perspective = 客观看待某事
- impart
  - 传授；告知
```

顶层无序列表项是 Point，其下是任意层级的释义或说明。导入前会预览；大小写不敏感的同名标题会跳过。

## 验证

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
```

测试中的 AI 请求由本地模拟题目替代，不消耗模型额度。实际复习需要可用的 AI 服务和密钥。

## 数据与范围

本地数据库默认位于 `data/point_review.sqlite3`，可用 `POINT_REVIEW_DB` 改位置。V1 固定为一个本地用户，没有登录、云同步和多人隔离；不要把服务直接暴露到公网。删除 Point 为逻辑删除，历史答题和结果仍保留。
