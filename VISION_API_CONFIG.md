# Vision API 配置指南 - 使用本地部署模型

本指南说明如何将 Suna 中的浏览器工具（Browser Tool）和视觉工具（Vision Tool）从 Google Gemini 替换为本地部署的视觉模型（如 Qwen3-VL）。

## 概述

默认情况下，Suna 的浏览器和视觉功能使用 Google Gemini API（需要 `GEMINI_API_KEY`）。现在您可以配置使用本地部署的 OpenAI 兼容模型，无需依赖云端服务。

## 配置步骤

### 1. 编辑 `.env` 文件

在您的 `backend/.env` 文件中，添加或修改以下配置：

```env
# 新的Vision API配置（优先级高于GEMINI_API_KEY）
VISION_API_KEY=sk-1234
VISION_API_ENDPOINT=http://api.openai.rnd.huawei.com
VISION_MODEL_ID=qwen3-vl-30b-a3b-instruct

# Gemini API Key 仍然作为备用选项（可选）
# GEMINI_API_KEY=
```

### 2. 配置参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `VISION_API_KEY` | Vision API 的抗体密钥 | `sk-1234` |
| `VISION_API_ENDPOINT` | Vision API 的基础 URL 地址 | `http://api.openai.rnd.huawei.com` |
| `VISION_MODEL_ID` | 使用的视觉模型 ID | `qwen3-vl-30b-a3b-instruct` |

## 工作原理

### 浏览器工具（Browser Tool）初始化流程

1. **API Key 检查**：
   ```
   使用 VISION_API_KEY? → 是 → 使用本地模型
                      → 否 → 使用 GEMINI_API_KEY（如配置）
                      → 都没有 → 报错
   ```

2. **初始化 Stagehand 服务**：
   - 浏览器工具向沙箱内的 Stagehand API 服务发送初始化请求
   - 传递参数：
     - `api_key`：从 `VISION_API_KEY` 或 `GEMINI_API_KEY`
     - `api_endpoint`：从 `VISION_API_ENDPOINT`（如果配置）
     - `model_id`：从 `VISION_MODEL_ID`（如果配置）

3. **请求格式示例**：
   ```json
   {
     "api_key": "sk-1234",
     "api_endpoint": "http://api.openai.rnd.huawei.com",
     "model_id": "qwen3-vl-30b-a3b-instruct"
   }
   ```

### 视觉工具（Vision Tool）初始化流程

视觉工具遵循相同的初始化流程，用于 SVG 转换和图像处理。

## 修改的文件清单

以下文件已修改以支持新的 Vision API 配置：

### 1. `backend/core/utils/config.py`
- 添加新配置字段：
  - `VISION_API_KEY`: Optional[str]
  - `VISION_API_ENDPOINT`: Optional[str]
  - `VISION_MODEL_ID`: Optional[str]

### 2. `backend/core/tools/browser_tool.py`
- 修改 `_check_stagehand_api_health()` 方法：
  - 检查 `VISION_API_KEY`，如果未配置则使用 `GEMINI_API_KEY`
  - 传递 `VISION_API_ENDPOINT` 和 `VISION_MODEL_ID` 到初始化端点
  
- 修改 `_execute_stagehand_api()` 方法：
  - 检查条件改为：`VISION_API_KEY` 或 `GEMINI_API_KEY` 之一配置

### 3. `backend/core/tools/sb_vision_tool.py`
- 修改 `convert_svg_with_sandbox_browser()` 方法：
  - 应用相同的 API key 和环境检查逻辑
  - 支持本地模型初始化参数传递

### 4. `backend/.env.example`
- 添加新的配置示例和说明注释

## 验证配置

启动 Suna 后，您可以通过以下方式验证配置：

1. **检查日志**：
   ```
   ✅ Stagehand API server is running and healthy
   ```

2. **测试浏览器工具**：
   - 在 Suna 中请求浏览器自动化操作
   - 确保返回成功的执行结果而非错误提示

3. **测试视觉工具**：
   - 上传图像进行分析
   - 观察是否使用了本地模型而非 Gemini

## 常见问题

### 问：如果同时配置了 VISION_API_KEY 和 GEMINI_API_KEY，哪个会被使用？
答：`VISION_API_KEY` 优先级更高。如果配置了 `VISION_API_KEY`，将使用该配置，否则回退到 `GEMINI_API_KEY`。

### 问：本地模型的 API 服务需要满足什么条件？
答：需要兼容 OpenAI API 格式的视觉端点。该模型应该能处理：
- 图像分析请求
- 网页截图分析
- SVG 到 PNG 的转换请求

### 问：需要重启 Suna 才能应用新配置吗？
答：是的，需要重启后端服务以加载新的环境变量。

### 问：VISION_API_ENDPOINT 和 VISION_MODEL_ID 是可选的吗？
答：
- `VISION_API_KEY`：必需（如果不用 Gemini）
- `VISION_API_ENDPOINT`：可选，如果提供则传递给初始化端点
- `VISION_MODEL_ID`：可选，如果提供则传递给初始化端点

## 后续步骤

1. **更新您的环境文件**：复制上述配置到 `backend/.env`
2. **重启后端服务**：确保新的环境变量被加载
3. **测试功能**：验证浏览器和视觉工具能正常工作
4. **监控日志**：检查是否有任何初始化错误

## 技术细节

### 初始化流程时序图

```
Suna Backend
    │
    ├─→ BrowserTool._execute_stagehand_api()
    │       │
    │       ├─→ 检查 VISION_API_KEY OR GEMINI_API_KEY
    │       │
    │       ├─→ _check_stagehand_api_health()
    │       │       │
    │       │       └─→ POST http://localhost:8004/api/init
    │       │           {
    │       │             "api_key": $VISION_API_KEY,
    │       │             "api_endpoint": $VISION_API_ENDPOINT,
    │       │             "model_id": $VISION_MODEL_ID
    │       │           }
    │       │
    │       └─→ POST http://localhost:8004/api/{endpoint}
    │
    └─→ 返回执行结果
```

## 支持

如有问题，请检查：
1. 环境变量是否正确设置
2. 本地 API 服务是否运行且可访问
3. Stagehand 沙箱服务是否正常初始化
4. 后端日志中是否有错误信息
