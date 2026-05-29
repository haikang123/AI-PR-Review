import sys
import os
import requests
from typing import Generator
import dashscope
from dashscope import Generation

# ===================== 全局UTF-8编码兼容 =====================
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

# 初始化通义千问
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")

# ===================== 通用工具函数 =====================
def safe_text(text: str) -> str:
    """字符串安全处理，兼容各类编码、非法字符"""
    if not isinstance(text, str):
        return str(text)
    return text.encode("utf-8", errors="replace").decode("utf-8")

# ===================== PR链接解析模块 =====================
def parse_pr_url(pr_url: str):
    """解析GitHub PR链接，支持http/https、www前缀"""
    try:
        pr_url = safe_text(pr_url.strip())
        if not pr_url.startswith(("http://", "https://")):
            raise ValueError("请输入完整HTTP/HTTPS格式链接")

        pr_url = pr_url.replace("://www.github.com/", "://github.com/")
        parts = pr_url.split("/")

        if len(parts) < 7 or parts[2] != "github.com" or parts[5] != "pull":
            raise ValueError("PR链接格式错误，示例：https://github.com/owner/repo/pull/123")

        owner = parts[3]
        repo = parts[4]
        pr_number = parts[6]

        if not pr_number.isdigit():
            raise ValueError("PR编号必须为数字")
        return owner, repo, pr_number
    except Exception as e:
        raise ValueError(f"链接解析失败: {safe_text(str(e))}")

# ===================== GitHub PR数据拉取模块（真实在线请求，适配国内弱网） =====================
def get_pr_details(owner: str, repo: str, pr_number: str, github_token: str):
    """调用GitHub官方API，拉取真实PR元数据 + 代码Diff"""
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-PR-Review-Assistant"
    }
    # 加长超时：连接15秒，读取40秒，适配国内访问GitHub延迟高的问题
    timeout = (15, 40)

    try:
        # 1. 获取PR基础元数据
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        resp = requests.get(api_url, headers=headers, timeout=timeout)

        if resp.status_code == 404:
            raise ValueError("PR 不存在、仓库不存在或为私有仓库（本工具仅支持公开PR）")
        elif resp.status_code == 401:
            raise ValueError("GitHub Token 无效，请检查 .env 配置")
        elif resp.status_code == 403:
            remain = resp.headers.get("X-RateLimit-Remaining", "0")
            reset_ts = resp.headers.get("X-RateLimit-Reset", "0")
            if remain == "0":
                raise ValueError(f"GitHub API 访问频次已达上限，请等待一段时间后重试")
            else:
                raise ValueError("Token 权限不足，无法访问该仓库")

        resp.raise_for_status()
        pr_data = resp.json()

        # 2. 获取官方Diff链接并拉取代码变更
        diff_url = pr_data.get("diff_url")
        if not diff_url:
            raise ValueError("无法获取本次PR的代码变更内容")

        diff_resp = requests.get(diff_url, headers=headers, timeout=timeout)
        diff_resp.raise_for_status()
        diff_resp.encoding = "utf-8"
        diff_text = safe_text(diff_resp.text)

        return pr_data, diff_text

    except requests.exceptions.Timeout:
        raise RuntimeError("访问 GitHub 超时，当前网络连接GitHub不稳定，可尝试切换网络/代理")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("无法连接 GitHub 服务器，请检查网络或开启代理")
    except Exception as e:
        raise RuntimeError(f"拉取PR数据失败: {safe_text(str(e))}")

# ===================== AI代码评审核心模块（通用Prompt，适配任意真实代码） =====================
def llm_review(pr_title: str, pr_body: str, diff_text: str) -> str:
    """调用通义千问，对任意真实PR代码做专业评审"""
    prompt = f"""
你是一名资深后端开发工程师与代码评审专家，请对这份真实 GitHub Pull Request 进行专业评审。
严格按照三段式输出，语言简洁专业，不要多余话术：
1. PR变更总结：简述本次代码修改的功能、范围与修改目的；
2. 风险代码识别：逐一指出代码中存在的BUG、逻辑问题、编码不规范、安全隐患、性能缺陷，并标注风险等级（高/中/低）；
3. 评审建议：针对发现的问题，给出具体、可落地的修复与优化建议。

=== PR标题 ===
{pr_title}
=== PR描述 ===
{pr_body}
=== 代码变更 Diff ===
{diff_text}
"""
    # 关闭流式输出，一次性返回完整结果，从源头避免内容拆分混乱
    response = Generation.call(
        model="qwen-turbo",
        messages=[{"role": "user", "content": prompt}],
        result_format="message",
        stream=False,
        temperature=0.1
    )

    if response.status_code == 200:
        return safe_text(response.output.choices[0].message.content)
    else:
        return f"大模型调用异常：{response.code} - {response.message}"

# ===================== 主执行入口 =====================
def run_pr_review(pr_url: str) -> Generator[str, None, None]:
    """完整评审流程：解析链接 → 拉取真实PR数据 → AI评审"""
    try:
        yield "🔍 正在解析PR链接..."
        owner, repo, pr_number = parse_pr_url(pr_url)
        
        yield "✅ PR链接解析成功"
        yield "🚀 正在从 GitHub 拉取代码变更数据（网络较慢请耐心等待）..."
        
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token or not github_token.strip():
            raise ValueError("未配置 GitHub Token，请检查 .env 文件")

        pr_data, diff_text = get_pr_details(owner, repo, pr_number, github_token.strip())
        yield "✅ 代码数据拉取完成"

        # 提取PR基础信息
        pr_title = safe_text(pr_data.get("title", "无标题"))
        pr_body = safe_text(pr_data.get("body", "无描述"))
        pr_user = safe_text(pr_data.get("user", {}).get("login", "未知作者"))
        changed_files = pr_data.get("changed_files", 0)
        additions = pr_data.get("additions", 0)
        deletions = pr_data.get("deletions", 0)

        # 拼接PR基础信息面板
        info_panel = f"""
---
📋 **PR 基础信息**
- 标题：{pr_title}
- 提交作者：{pr_user}
- 变更文件数：{changed_files} 个
- 新增代码：{additions} 行
- 删除代码：{deletions} 行
---
🤖 AI 正在分析代码并生成评审报告，请稍候...
"""
        yield info_panel

        # 调用大模型评审真实代码
        final_report = llm_review(pr_title, pr_body, diff_text)
        yield final_report

    except Exception as e:
        err_msg = safe_text(str(e))
        yield f"❌ {err_msg}"