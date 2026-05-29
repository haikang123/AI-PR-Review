import streamlit as st
import sys
import os
import logging
from dotenv import load_dotenv

# ===================== 全局UTF-8编码 =====================
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
os.environ["PYTHONUTF8"] = "1"
os.environ["LC_ALL"] = "en_US.UTF-8"
os.environ["LANG"] = "en_US.UTF-8"
os.environ["PYTHONIOENCODING"] = "utf-8"

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 通用字符串处理
def safe_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return text.encode("utf-8", errors="replace").decode("utf-8")

# 加载环境变量
try:
    load_dotenv(encoding="utf-8", override=True)
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

    if not DASHSCOPE_API_KEY or not GITHUB_TOKEN:
        raise ValueError("密钥配置缺失")
    logger.info("环境变量加载成功")
except Exception as e:
    err = safe_text(str(e))
    st.error(f"❌ 环境配置失败：{err}")
    st.info("请检查根目录 .env 文件中的密钥配置")
    sys.exit(1)

# 导入核心逻辑
try:
    from agent import run_pr_review
except Exception as e:
    err = safe_text(str(e))
    st.error(f"❌ 加载核心模块失败：{err}")
    st.stop()

# ===================== 页面初始化 =====================
st.set_page_config(
    page_title="AI PR Review 智能代码评审助手",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Session 状态管理
if "is_reviewing" not in st.session_state:
    st.session_state.is_reviewing = False
if "final_report" not in st.session_state:
    st.session_state.final_report = ""
if "last_pr_url" not in st.session_state:
    st.session_state.last_pr_url = ""

# 侧边栏
with st.sidebar:
    st.markdown("## 🤖 AI PR Review 助手")
    st.markdown("### 功能介绍")
    st.markdown("- 在线拉取 GitHub 公开 PR 代码")
    st.markdown("- AI 智能分析代码、识别风险")
    st.markdown("- 输出变更总结、风险点、评审建议")
    st.markdown("---")
    st.markdown("### 使用说明")
    st.markdown("1. 输入任意公开 GitHub PR 链接")
    st.markdown("2. 点击「开始智能评审」")
    st.markdown("3. 等待加载并查看评审报告")
    st.markdown("---")
    st.markdown("### 测试链接（可直接复制使用）")
    st.code("https://github.com/521xueweihan/HelloGitHub/pull/3232")
    st.code("https://github.com/python/cpython/pull/100000")

# 主页面
st.title("🔍 AI PR Review 智能代码评审助手")
st.markdown("---")

pr_url = st.text_input(
    "请输入 GitHub 公开 PR 完整链接",
    placeholder="https://github.com/仓库所有者/仓库名/pull/编号",
    disabled=st.session_state.is_reviewing,
    value=st.session_state.last_pr_url
)

col1, col2 = st.columns([1, 5])
with col1:
    start_btn = st.button(
        "开始智能评审",
        type="primary",
        disabled=st.session_state.is_reviewing or not pr_url.strip(),
        use_container_width=True
    )

st.markdown("---")

# 分区渲染：临时状态区 + 最终报告区（核心防重复）
status_area = st.empty()
report_area = st.container()

# 触发评审
if start_btn and pr_url.strip():
    st.session_state.last_pr_url = pr_url.strip()
    st.session_state.is_reviewing = True
    st.session_state.final_report = ""
    st.rerun()

# 执行评审逻辑
if st.session_state.is_reviewing:
    try:
        full_report = ""
        for content in run_pr_review(st.session_state.last_pr_url):
            content = safe_text(content)
            full_report = content
            # 临时状态实时刷新
            status_area.info(content)

        # 加载完成：清空状态提示，只展示最终报告
        status_area.empty()
        st.session_state.final_report = full_report
        report_area.markdown(full_report)
        logger.info("PR 评审完成")

    except Exception as e:
        err = safe_text(str(e))
        status_area.error(f"❌ {err}")
    finally:
        st.session_state.is_reviewing = False
        if st.button("重新评审", use_container_width=True):
            st.session_state.is_reviewing = True
            st.rerun()

# 展示历史评审结果
elif st.session_state.final_report:
    report_area.markdown(st.session_state.final_report)
    if st.button("重新评审", use_container_width=True):
        st.session_state.is_reviewing = True
        st.rerun()