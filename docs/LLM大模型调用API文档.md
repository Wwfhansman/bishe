ARK_API_KEY:9eefa037-8365-4169-ab2d-dc8612fef8d2


本文帮助您快速完成 API 调用模型，包括配置环境、使用 SDK 。
> 快速入口：

> * 直接体验模型能力，访问 [模型广场](https://console.volcengine.com/ark/region:ark+cn-beijing/experience)
> * 有模型调用经验，查看教程[文本生成](/docs/82379/1399009)。
> * 业务从 OpenAI 迁移至方舟，查看[兼容 OpenAI SDK](/docs/82379/1330626)。

<span id="da0e9d90"></span>
# 使用流程
通过代码调用模型服务，可以分为以下几步：

* [1.获取并配置 API Key ](/docs/82379/1399008#b00dee71)
* [2.获取 Model ID](/docs/82379/1399008#1008bfdb)
* [3.配置环境并发起调用](/docs/82379/1399008#99a7c9ca)

<span id="b00dee71"></span>
# 1.获取 API Key 
<span id="10d67aef"></span>
## 获取 API Key

1. 打开并登录[API Key 管理](https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey) 页面。
2. （可选）单击左上角 **账号全部资源** 下拉箭头，切换项目空间。
3. 单击 **创建 API Key** 按钮。
4. 在弹出框的 **名称** 文本框中确认/更改 API Key名称，单击创建。

您可以在[API Key 管理](https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey) 页面的 **API Key 列表**中查看刚创建的API Key信息。
:::tip
如使用 Access Key，请参见 [Base URL及鉴权](/docs/82379/1298459)。
:::
<span id="4b62407d"></span>
## 配置 API Key 到环境变量
建议配置 API Key 到环境变量，避免在代码中明文输入 API Key，降低泄漏风险。
完整说明请参见 [环境变量配置指南](/docs/82379/1820161)。

```mixin-react
return (<Tabs>
<Tabs.TabPane title="MacOS" key="jwSdYoMfTR"><RenderMd content={`仅在当前会话中使用 API Key 环境变量，可以添加临时环境变量。

1. 打开终端使用以下命令来设置环境变量，将\`<ARK_API_KEY>\`替换为您的方舟 API Key。

\`\`\`Shell
export ARK_API_KEY="<ARK_API_KEY>"
\`\`\`


2. 执行以下命令，验证该环境变量是否生效。

\`\`\`Shell
echo $ARK_API_KEY
\`\`\`

`}></RenderMd></Tabs.TabPane>
<Tabs.TabPane title="Linux" key="GcZKLllwLv"><RenderMd content={`在当前会话中使用该环境变量，可以添加临时性环境变量。

1. 打开终端使用以下命令来设置环境变量，将\`<ARK_API_KEY>\`替换为您的方舟 API Key。

\`\`\`Shell
export ARK_API_KEY="<ARK_API_KEY>"
\`\`\`


2. 执行以下命令，验证该环境变量是否生效。

\`\`\`Shell
echo $ARK_API_KEY
\`\`\`

`}></RenderMd></Tabs.TabPane>
<Tabs.TabPane title="Windows" key="SwuIQng4bn"><RenderMd content={`在当前会话中使用该环境变量，可以添加临时性环境变量。
<span id="c766b95f"></span>
#### 在 CMD 中

1. 打开 CMD（命令提示符） 。
2. 输入以下命令来设置环境变量，将\`<ARK_API_KEY>\`替换为您的实际 API Key：
   \`\`\`Shell
   set ARK_API_KEY=<ARK_API_KEY>
   \`\`\`

3. 验证环境变量是否设置成功，输入以下命令，如果返回您的 API Key，则表示设置成功。
   \`\`\`Shell
   echo %ARK_API_KEY%
   \`\`\`


<span id="ed024eb1"></span>
#### 在 PowerShell 中

1. 打开 PowerShell 。
2. 输入以下命令来设置环境变量，将\`<ARK_API_KEY>\`替换为您的实际 API Key：
   \`\`\`PowerShell
   $env:ARK_API_KEY = "<ARK_API_KEY>"
   \`\`\`

3. 验证环境变量是否设置成功，输入以下命令，如果返回您的 API Key，则表示设置成功。
   \`\`\`Shell
   $env:ARK_API_KEY
   \`\`\`

`}></RenderMd></Tabs.TabPane></Tabs>);
 ```

<span id="1008bfdb"></span>
# 2.获取 Model ID
通过 Model ID 快速调用模型。

1. 查看 [模型列表](/docs/82379/1330310) 获取所需模型的 ID（Model ID）。
2. 访问[开通管理页面](https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement) 开通对应模型服务。

:::tip
如是多应用、企业用户等场景，推荐通过 Endpoint ID 来调用模型，具体可参考[获取 Endpoint ID](/docs/82379/1099522#b35cee81)。
:::
<span id="99a7c9ca"></span>
# 3.配置环境并发起调用
 [Curl](/docs/82379/1399008#a7831f97)  <span style="color: #646a73"><strong>｜</strong></span>[Python](/docs/82379/1399008#2832b836)  **｜**   [Go](/docs/82379/1399008#3fc72e6d)  <span style="color: #646a73"> </span><span style="color: #646a73"><strong>｜</strong></span><span style="color: #646a73"> </span> [Java](/docs/82379/1399008#0009f01e)
选择熟悉和方便的语言调用模型推理服务。
<span id="a7831f97"></span>
## Curl
通过 HTTP 方式直接调用方舟模型服务。
在终端窗口中，复制并运行下面命令，稍等可在终端窗口中看到模型调用的返回结果。这样就完成了首次方舟平台模型服务调用。

```mixin-react
return (<Tabs>
<Tabs.TabPane title="macOS / Linux" key="UDLCZJhdI9"><RenderMd content={`\`\`\`Shell
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $ARK_API_KEY" \\
  -d '{
    "model": "doubao-seed-1-6-251015",
    "messages": [
        {
            "role": "user",
            "content": "hello"
        }
    ]
  }'
\`\`\`

`}></RenderMd></Tabs.TabPane>
<Tabs.TabPane title="Windows CMD" key="aLJn90sXsV"><RenderMd content={`\`\`\`Shell
curl -X POST "https://ark.cn-beijing.volces.com/api/v3/chat/completions" ^
-H "Authorization: Bearer %ARK_API_KEY%" ^
-H "Content-Type: application/json" ^
-d "{
    \\"model\\": \\"doubao-seed-1-6-251015\\",
    \\"messages\\": [
        {
            \\"role\\": \\"user\\",
            \\"content\\": \\"hello\\"
        }
    ]
}"
\`\`\`

`}></RenderMd></Tabs.TabPane>
<Tabs.TabPane title="Windows PowerShell" key="Qdh31MWd2d"><RenderMd content={`\`\`\`Shell
curl.exe https://ark.cn-beijing.volces.com/api/v3/chat/completions \`
-H "Authorization: Bearer $env:ARK_API_KEY" \`
-H "Content-Type: application/json" \`
-d '{
    \\"model\\": \\"doubao-seed-1-6-251015\\",
    \\"messages\\": [
        {
            \\"role\\": \\"user\\",
            \\"content\\": \\"hello\\"
        }
    ]
}'
\`\`\`

`}></RenderMd></Tabs.TabPane></Tabs>);
 ```


> * 如果返回错误码 `{"error":{"code":"AuthenticationError","message":"The API key or AK/SK in the request is missing or invalid. requestId: 0217***`，说明 API Key 没有被正确设置到环境变量中，检查您的环境配置或直接替换`$ARK_API_KEY`为 API Key ，再次运行命令。

<span id="2832b836"></span>
## Python

1. 检查并安装 3.7 或以上版本 Python。
   在终端输入以下命令检查 Python 版本：
   ```Shell
   python -V
   ```

   如运行失败，请尝试命令：
   ```Shell
   python3 -V
   ```

   如果未安装或者版本不满足，请参考 [Python 安装教程](https://www.python.org/downloads/)。



```mixin-react
return (<Tabs>
<Tabs.TabPane title="方舟 Python SDK" key="dUU11SVzcx"><RenderMd content={`2. 安装/升级方舟 Python SDK。
   \`\`\`Bash
   # 安装
   pip install 'volcengine-python-sdk[ark]'
   # 升级
   pip install 'volcengine-python-sdk[ark]' -U
   \`\`\`

   如安装错误，可尝试使用下面命令安装。
   \`\`\`Bash
   # 安装
   pip install volcengine-python-sdk[ark]
   # 升级
   pip install -U volcengine-python-sdk[ark]
   \`\`\`

   * [Windows系统安装SDK失败，ERROR: Failed building wheel for volcengine-python-sdk](/docs/82379/1359411#b74e8ad6)
3. 创建\`ark_example.py\`文件，复制下面示例代码进文件。
   \`\`\`Python
   import os
   from volcenginesdkarkruntime import Ark
   
   client = Ark(
       api_key=os.environ.get("ARK_API_KEY"),
       # The base URL for model invocation .
       base_url="https://ark.cn-beijing.volces.com/api/v3",
       )
   completion = client.chat.completions.create(
       # Replace with Model ID .
       model="doubao-seed-1-6-251015",
       messages=[
           {"role": "user", "content": "Hello"}
       ]
   )
   print(completion.choices[0].message)
   \`\`\`

4. 在终端输入下面命令，运行代码。
   \`\`\`Shell
   python ark_example.py
   \`\`\`

5. 稍等在终端窗口中会打印调用结果。这样你完成了首次模型服务调用。
`}></RenderMd></Tabs.TabPane>
<Tabs.TabPane title="OpenAI SDK" key="yXhLaiNErS"><RenderMd content={`2. 安装 OpenAI SDK。
   在终端中输入以下命令，安装/升级 OpenAI SDK：
   \`\`\`Shell
   # 安装
   pip install openai
   # 升级
   pip install -U openai
   \`\`\`

3. 创建\`ark_example.py\`文件，复制示例代码进文件。
   \`\`\`Python
   import os
   from openai import OpenAI
   
   client = OpenAI(
       # Make sure the environment variable "ARK_API_KEY" has been set.
       api_key=os.environ.get("ARK_API_KEY"), 
       # The base URL for model invocation .
       base_url="https://ark.cn-beijing.volces.com/api/v3",
       )
   completion = client.chat.completions.create(
       # Replace with Model ID .
       model="doubao-seed-1-6-251015",
       messages=[
           {"role": "user", "content": "hello"}
       ]
   )
   print(completion.choices[0].message)
   \`\`\`

4. 在终端输入下面命令，运行代码。
   \`\`\`Shell
   python ark_example.py
   \`\`\`

   稍等，终端窗口中会打印模型调用结果。这样你完成了首次模型服务调用。
`}></RenderMd></Tabs.TabPane></Tabs>);
 ```

<span id="3fc72e6d"></span>
## Go

1. 检查 Go 版本，需 1.18 或以上。
   ```Shell
   go version
   ```

   如果未安装 Go 或者版本不满足要求，参考[文档](https://golang.google.cn/doc/install)安装 1.18 或以上版本 Go。
2. 安装方舟 Go SDK。
   方舟 Go SDK 使用 go mod 进行管理。运行以下命令初始化工程。替换`<YOUR_PROJECT_NAME>`为您的项目名称。
   ```Shell
   go mod init <YOUR_PROJECT_NAME>
   ```

   运行以下命令安装方舟 Go SDK。
   ```Shell
   go get -u github.com/volcengine/volcengine-go-sdk 
   ```

3. 创建一个`main.go`文件，复制下面代码到文件。
   ```Go
   package main
   
   import (
       "context"
       "fmt"
       "os"
       "github.com/volcengine/volcengine-go-sdk/service/arkruntime"
       "github.com/volcengine/volcengine-go-sdk/service/arkruntime/model"
       "github.com/volcengine/volcengine-go-sdk/volcengine"
   )
   
   func main() {
       client := arkruntime.NewClientWithApiKey(
           os.Getenv("ARK_API_KEY"),
           arkruntime.WithBaseUrl("https://ark.cn-beijing.volces.com/api/v3"),  // The base URL for model invocation .
       )
       // 创建一个上下文，通常用于传递请求的上下文信息，如超时、取消等
       ctx := context.Background()
       // 构建聊天完成请求，设置请求的模型和消息内容
       req := model.CreateChatCompletionRequest{
          Model: "doubao-seed-1-6-251015", // Replace with Model ID .
          Messages: []*model.ChatCompletionMessage{
             {
                // 消息的角色为用户
                Role: model.ChatMessageRoleUser,
                Content: &model.ChatCompletionMessageContent{
                   StringValue: volcengine.String("hello"),
                },
             },
          },
       }
       // 发送聊天完成请求，并将结果存储在 resp 中，将可能出现的错误存储在 err 中
       resp, err := client.CreateChatCompletion(ctx, req)
       if err!= nil {
          // 若出现错误，打印错误信息并终止程序
          fmt.Printf("standard chat error: %v\n", err)
          return
       }
       // 打印聊天完成请求的响应结果
       fmt.Println(*resp.Choices[0].Message.Content.StringValue)
   }
   ```

4. 在终端运行下面命令，更新项目的依赖项。
   ```Shell
   go mod tidy
   ```

5. 执行下面命令，运行代码。
   ```Shell
   go run main.go
   ```

6. 稍等，终端中打印模型调用结果。这样您完成了首次模型服务调用。

<span id="0009f01e"></span>
## Java

1. 检查 Java 版本，需要 1.8 或以上。
   ```Shell
   java -version
   ```

   如果未安装 Java 或者版本不满足要求，访问[网站](https://www.java.com/en/download/help/index_installing.html)下载并安装 Java，请确保选择 1.8 或以上版本。
2. 安装方舟 Java SDK。
   方舟 Java SDK 支持通过 [Maven](https://maven.apache.org/install.html) 和 [Gradle](https://gradle.org/install/) 两种方式安装。
   * 通过 [Maven](https://maven.apache.org) 安装：在项目的`pom.xml`文件中添加以下依赖配置。
      ```XML
      ...
      <dependency>
        <groupId>com.volcengine</groupId>
        <artifactId>volcengine-java-sdk-ark-runtime</artifactId>
        <version>LATEST</version>
      </dependency>
      ...
      ```

      打开终端并进入项目根目录，运行下面命令，来安装依赖项。
      ```Shell
      mvn clean install
      ```

   * 通过 [Gradle](https://gradle.org/) 安装：在项目的`build.gradle`文件中，在`dependencies`部分添加以下依赖。
      ```JSON
      implementation 'com.volcengine:volcengine-java-sdk-ark-runtime:LATEST'
      ```

   :::tip
   获取 SDK 版本信息，替换'LATEST' 为指定/最新版本号。可查询：https://github.com/volcengine/volcengine-java-sdk/releases
   :::
3. 将下面的示例代码复制到您的项目中。
   ```Java
   package com.ark.example;
   
   import com.volcengine.ark.runtime.model.completion.chat.ChatCompletionRequest;
   import com.volcengine.ark.runtime.model.completion.chat.ChatMessage;
   import com.volcengine.ark.runtime.model.completion.chat.ChatMessageRole;
   import com.volcengine.ark.runtime.service.ArkService;
   import java.util.ArrayList;
   import java.util.List;
   
   /**
    * 这是一个示例类，展示了如何使用ArkService来完成聊天功能。
    */
   public class ChatCompletionsExample {
       public static void main(String[] args) {
           // 从环境变量中获取API密钥
           String apiKey = System.getenv("ARK_API_KEY");        
           //  .
           ArkService arkService = ArkService.builder().apiKey(apiKey).baseUrl("https://ark.cn-beijing.volces.com/api/v3").build();
           
           // 初始化消息列表
           List<ChatMessage> chatMessages = new ArrayList<>();
           
           // 创建用户消息
           ChatMessage userMessage = ChatMessage.builder()
                   .role(ChatMessageRole.USER) // 设置消息角色为用户
                   .content("hello") // 设置消息内容
                   .build();
           
           // 将用户消息添加到消息列表
           chatMessages.add(userMessage);
           
           // 创建聊天完成请求
           ChatCompletionRequest chatCompletionRequest = ChatCompletionRequest.builder()
                   .model("doubao-seed-1-6-251015") // Replace with Model ID
                   .messages(chatMessages) // 设置消息列表
                   .build();
           
           // 发送聊天完成请求并打印响应
           try {
               // 获取响应并打印每个选择的消息内容
               arkService.createChatCompletion(chatCompletionRequest)
                        .getChoices()
                        .forEach(choice -> System.out.println(choice.getMessage().getContent()));
           } catch (Exception e) {
               System.out.println("Error: " + e.getMessage());
           } finally {
               // 关闭服务执行器
               arkService.shutdownExecutor();
           }
       }
   }
   ```

4. 编译您的 Java 项目并运行。
5. 稍等，终端窗口中会打印模型调用的结果。这样您就完成了首次模型服务调用。

<span id="ffac0939"></span>
# 下一步
现在你已经完成了首次方舟模型服务的 API 调用，你可以探索模型的更多能力，包括：

* [平台能力速览](/docs/82379/1108216)：探索方舟平台提供的提示词优化、权限管理、模型管理等高阶能力。
* [模型列表](/docs/82379/1330310)：快速浏览方舟提供的模型全集以及各个模型所具备的能力，快速根据你的实际场景匹配到合适的模型。



