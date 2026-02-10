# 快速开始 - 替换 Gemini 为本地部署模型

## 1. 更新环境配置

编辑 `backend/.env` 文件，添加以下配置：

```env
# 本地部署模型配置
VISION_API_KEY=sk-1234
VISION_API_ENDPOINT=http://api.openai.rnd.huawei.com
VISION_MODEL_ID=qwen3-vl-30b-a3b-instruct
```

## 2. 重启后端服务

```bash
# 重启 Suna 后端
cd backend
python start.py
```

## 3. 验证配置

启动后，检查日志中是否出现：
```
✅ Stagehand API server is running and healthy
```

## 配置优先级

系统会按以下优先级使用 API Key：

1. **VISION_API_KEY** (优先) - 本地部署模型
2. **GEMINI_API_KEY** (备用) - Google Gemini
3. 如果都未配置，浏览器和视觉工具将不可用

## 初始化流程

当浏览器或视觉工具首次被调用时，会向本地 Stagehand 服务发送以下初始化请求：

```json
{
  "api_key": "sk-1234",
  "api_endpoint": "http://api.openai.rnd.huawei.com",
  "model_id": "qwen3-vl-30b-a3b-instruct"
}
```

## 修改的文件

- ✅ `backend/core/utils/config.py` - 添加新配置字段
- ✅ `backend/core/tools/browser_tool.py` - 使用新配置初始化
- ✅ `backend/core/tools/sb_vision_tool.py` - 使用新配置初始化
- ✅ `backend/.env.example` - 添加配置示例

## 常见问题

**Q: 到底修改了什么？**
A: 现在浏览器工具和视觉工具不再硬编码依赖 GEMINI_API_KEY，而是优先使用 VISION_API_KEY（如果配置），并支持传递自定义的 API endpoint 和 model ID。

**Q: 必须配置 VISION_API_ENDPOINT 和 VISION_MODEL_ID 吗？**
A: 不必须。只有 VISION_API_KEY 是必需的（如果不使用 Gemini）。endpoint 和 model ID 如果配置就会被传递给初始化服务，否则服务可能有自己的默认值。

**Q: 如果同时配置了 VISION_API_KEY 和 GEMINI_API_KEY？**
A: 优先使用 VISION_API_KEY。GEMINI_API_KEY 仅作为备用。

**Q: 需要修改 Stagehand 服务吗？**
A: Stagehand 服务需要支持接收新的初始化参数。查看 [VISION_API_CONFIG.md](VISION_API_CONFIG.md) 了解详细技术细节。

## 更多信息

详见 [VISION_API_CONFIG.md](VISION_API_CONFIG.md) 获取完整的技术文档。
