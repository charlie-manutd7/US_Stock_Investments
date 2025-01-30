import os
import time
import logging
import google.generativeai as genai
from dotenv import load_dotenv
from dataclasses import dataclass
import backoff
from typing import Optional, Dict, Any
from agents.state import AgentState, show_agent_reasoning

# 设置日志记录
logger = logging.getLogger('api_calls')
logger.setLevel(logging.DEBUG)

# 移除所有现有的处理器
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 创建日志目录
log_dir = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), 'logs')
os.makedirs(log_dir, exist_ok=True)

# 设置文件处理器
log_file = os.path.join(log_dir, f'api_calls_{time.strftime("%Y%m%d")}.log')
print(f"Creating log file at: {log_file}")

try:
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_handler.setLevel(logging.DEBUG)
    print("Successfully created file handler")
except Exception as e:
    print(f"Error creating file handler: {str(e)}")

# 设置控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# 设置日志格式
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 添加处理器
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 立即测试日志记录
logger.debug("Logger initialization completed")
logger.info("API logging system started")

# 状态图标
SUCCESS_ICON = "✓"
ERROR_ICON = "✗"
WAIT_ICON = "⟳"


@dataclass
class ChatMessage:
    content: str


@dataclass
class ChatChoice:
    message: ChatMessage


@dataclass
class ChatCompletion:
    choices: list[ChatChoice]


# 获取项目根目录
project_root = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
env_path = os.path.join(project_root, '.env')

# 加载环境变量
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
    logger.info(f"{SUCCESS_ICON} 已加载环境变量: {env_path}")
else:
    logger.warning(f"{ERROR_ICON} 未找到环境变量文件: {env_path}")

# 验证环境变量
api_key = os.getenv("GEMINI_API_KEY")
model = os.getenv("GEMINI_MODEL")

if not api_key:
    logger.error(f"{ERROR_ICON} 未找到 GEMINI_API_KEY 环境变量")
    raise ValueError("GEMINI_API_KEY not found in environment variables")
if not model:
    model = "gemini-1.5-flash"
    logger.info(f"{WAIT_ICON} 使用默认模型: {model}")

# 初始化 Gemini 客户端
genai.configure(api_key=api_key)
logger.info(f"{SUCCESS_ICON} Gemini API 配置成功")


@backoff.on_exception(
    backoff.expo,
    (Exception),
    max_tries=5,
    max_time=300,
    giveup=lambda e: "AFC is enabled" not in str(e)
)
def generate_content_with_retry(model_name, contents, config=None):
    """带重试机制的内容生成函数"""
    try:
        logger.info(f"{WAIT_ICON} 正在调用 Gemini API...")
        logger.info(f"请求内容: {contents[:500]}..." if len(
            str(contents)) > 500 else f"请求内容: {contents}")
        logger.info(f"请求配置: {config}")

        model = genai.GenerativeModel(model_name)
        
        # Extract system instruction if present
        generation_config = {}
        if config and 'system_instruction' in config:
            system_prompt = config.pop('system_instruction')
            contents = f"{system_prompt}\n\n{contents}"
            generation_config = config

        response = model.generate_content(
            contents,
            generation_config=generation_config if generation_config else None
        )

        logger.info(f"{SUCCESS_ICON} API 调用成功")
        logger.info(f"响应内容: {response.text[:500]}..." if len(
            str(response.text)) > 500 else f"响应内容: {response.text}")
        return response
    except Exception as e:
        if "AFC is enabled" in str(e):
            logger.warning(f"{ERROR_ICON} 触发 API 限制，等待重试... 错误: {str(e)}")
            time.sleep(5)
            raise e
        logger.error(f"{ERROR_ICON} API 调用失败: {str(e)}")
        logger.error(f"错误详情: {str(e)}")
        raise e


def get_chat_completion(messages, model=None, max_retries=3, initial_retry_delay=1):
    """获取聊天完成结果，包含重试逻辑"""
    try:
        if model is None:
            model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

        logger.info(f"{WAIT_ICON} 使用模型: {model}")
        logger.debug(f"消息内容: {messages}")

        for attempt in range(max_retries):
            try:
                # 转换消息格式
                prompt = ""
                system_instruction = None

                for message in messages:
                    role = message["role"]
                    content = message["content"]
                    if role == "system":
                        system_instruction = content
                    elif role == "user":
                        prompt += f"User: {content}\n"
                    elif role == "assistant":
                        prompt += f"Assistant: {content}\n"

                # 准备配置
                config = {}
                if system_instruction:
                    config['system_instruction'] = system_instruction

                # 调用 API
                response = generate_content_with_retry(
                    model_name=model,
                    contents=prompt.strip(),
                    config=config
                )

                if response is None:
                    logger.warning(
                        f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries}: API 返回空值")
                    if attempt < max_retries - 1:
                        retry_delay = initial_retry_delay * (2 ** attempt)
                        logger.info(f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                        continue
                    return None

                # 转换响应格式
                chat_message = ChatMessage(content=response.text)
                chat_choice = ChatChoice(message=chat_message)
                completion = ChatCompletion(choices=[chat_choice])

                logger.debug(f"API 原始响应: {response.text}")
                logger.info(f"{SUCCESS_ICON} 成功获取响应")
                return completion.choices[0].message.content

            except Exception as e:
                logger.error(
                    f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries} 失败: {str(e)}")
                if attempt < max_retries - 1:
                    retry_delay = initial_retry_delay * (2 ** attempt)
                    logger.info(f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"{ERROR_ICON} 最终错误: {str(e)}")
                    return None

    except Exception as e:
        logger.error(f"{ERROR_ICON} get_chat_completion 发生错误: {str(e)}")
        return None


def get_industry_metrics(ticker: str) -> dict:
    """
    Get industry-specific metrics for valuation adjustments.
    This function provides industry averages, company positioning, and competitive moat analysis.
    """
    # Technology sector leaders with wide moats
    tech_leaders_wide_moat = {'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'}
    
    # Technology sector leaders with narrow moats
    tech_leaders_narrow_moat = {'NVDA', 'AVGO', 'ORCL', 'CRM', 'ADBE'}
    
    # Technology challengers with narrow moats
    tech_challengers = {'AMD', 'INTC', 'TSM', 'QCOM', 'TXN', 'MU', 'AMAT', 'KLAC', 'LRCX', 'ASML'}
    
    # Semiconductor industry metrics with enhanced margins data
    semiconductor_metrics = {
        'pe_ratio': 25,  # Higher PE due to growth and cyclicality
        'growth_rate': 0.15,  # Strong growth expectations
        'market_position': 'average',
        'industry_margins': {
            'gross_margin': 0.45,  # Semiconductor industry average
            'operating_margin': 0.25,
            'net_margin': 0.20
        }
    }
    
    # Technology sector metrics with enhanced margins data
    tech_metrics = {
        'pe_ratio': 30,  # Higher PE for tech sector
        'growth_rate': 0.20,  # Strong growth expectations
        'market_position': 'average',
        'industry_margins': {
            'gross_margin': 0.60,  # Tech industry average
            'operating_margin': 0.30,
            'net_margin': 0.25
        }
    }
    
    # Default metrics for other industries
    default_metrics = {
        'pe_ratio': 20,
        'growth_rate': 0.10,
        'market_position': 'average',
        'industry_margins': {
            'gross_margin': 0.40,
            'operating_margin': 0.15,
            'net_margin': 0.10
        }
    }
    
    # Determine company's market position and moat
    if ticker in tech_leaders_wide_moat:
        market_position = 'leader'
        competitive_moat = 'wide'
    elif ticker in tech_leaders_narrow_moat:
        market_position = 'leader'
        competitive_moat = 'narrow'
    elif ticker in tech_challengers:
        market_position = 'challenger'
        competitive_moat = 'narrow'
    else:
        market_position = 'average'
        competitive_moat = 'none'
    
    # Select appropriate industry metrics
    if ticker in {'NVDA', 'AMD', 'INTC', 'TSM', 'QCOM'}:
        metrics = semiconductor_metrics.copy()
    elif ticker in tech_leaders_wide_moat.union(tech_leaders_narrow_moat, tech_challengers):
        metrics = tech_metrics.copy()
    else:
        metrics = default_metrics.copy()
    
    # Update market position and competitive moat
    metrics['market_position'] = market_position
    metrics['competitive_moat'] = competitive_moat
    
    # Adjust metrics based on market position and moat
    if market_position == 'leader':
        metrics['pe_ratio'] *= 1.2  # 20% premium for leaders
        metrics['growth_rate'] *= 1.2  # 20% higher growth expectations
        # Adjust margins for market leaders
        for margin_type in metrics['industry_margins']:
            metrics['industry_margins'][margin_type] *= 1.2
    elif market_position == 'challenger':
        metrics['pe_ratio'] *= 1.1  # 10% premium for challengers
        metrics['growth_rate'] *= 1.1  # 10% higher growth expectations
        # Adjust margins for challengers
        for margin_type in metrics['industry_margins']:
            metrics['industry_margins'][margin_type] *= 1.1
    
    # Additional premium for wide moat companies
    if competitive_moat == 'wide':
        metrics['pe_ratio'] *= 1.15  # Additional 15% premium for wide moat
        metrics['growth_rate'] *= 1.1  # Additional 10% growth premium
        # Higher margins for wide moat companies
        for margin_type in metrics['industry_margins']:
            metrics['industry_margins'][margin_type] *= 1.15
    elif competitive_moat == 'narrow':
        metrics['pe_ratio'] *= 1.1  # Additional 10% premium for narrow moat
        metrics['growth_rate'] *= 1.05  # Additional 5% growth premium
        # Slightly higher margins for narrow moat companies
        for margin_type in metrics['industry_margins']:
            metrics['industry_margins'][margin_type] *= 1.1
    
    return metrics
