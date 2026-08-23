"""
RWA 创业信息简报系统
邮件发送模块
"""
import os
import socket
import logging
import smtplib
import ssl
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional

import markdown

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _create_proxy_socket(host: str, port: int, timeout: int = 30) -> Optional[socket.socket]:
    """
    若环境存在HTTP代理(HTTP_PROXY/http_proxy)，则通过代理CONNECT隧道建立TCP连接。
    否则返回None（交由smtplib直接连接）。
    """
    proxy_url = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not proxy_url:
        return None

    # 解析代理地址 host:port
    proxy_host = proxy_url.replace("http://", "").replace("https://", "")
    if "@" in proxy_host:  # 处理 user:pass@host:port 格式
        proxy_host = proxy_host.split("@")[-1]
    parts = proxy_host.split(":")
    proxy_addr = parts[0]
    proxy_port = int(parts[1]) if len(parts) > 1 else 8080

    try:
        import socks
    except ImportError:
        logger.warning("检测到代理但未安装PySocks，尝试直连...")
        return None

    try:
        s = socks.socksocket()
        s.set_proxy(socks.HTTP, proxy_addr, proxy_port)
        s.settimeout(timeout)
        s.connect((host, port))
        logger.info(f"代理隧道连接已建立: {host}:{port} (via {proxy_addr}:{proxy_port})")
        return s
    except Exception as e:
        logger.warning(f"代理隧道连接失败: {e}，尝试直连...")
        return None


class EmailSender:
    """邮件发送器（支持SMTP）"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.push_config = config.get("push", {})
        self.sender_config = self.push_config.get("email_sender", {})
        
        # 从环境变量获取凭据
        self.smtp_user = os.environ.get(
            self.sender_config.get("smtp_user_env", "SMTP_USER"),
            ""
        )
        self.smtp_password = os.environ.get(
            self.sender_config.get("smtp_password_env", "SMTP_PASSWORD"),
            ""
        )
    
    def should_send(self, events: List[Any]) -> bool:
        """
        根据推送频率，判断本期是否应该发送
        
        Args:
            events: 处理后的事件列表
            
        Returns:
            True=应该发送邮件
        """
        frequency = self.push_config.get("frequency", "daily")
        
        if frequency == "daily":
            # 每日推送：只要有内容就发
            return len(events) > 0
        
        elif frequency == "major_only":
            # 仅重大事件推送：有高优先级或融资>阈值才发
            has_high = any(e.importance == "high" for e in events)
            threshold = self.config["FUNDING_THRESHOLD"]["MAJOR"]
            has_big_funding = any(
                (e.funding_amount or 0) >= threshold for e in events
            )
            should = has_high or has_big_funding
            if not should:
                logger.info("推送模式=仅重大事件，本期无重大事件，跳过发送")
            return should
        
        elif frequency == "weekly":
            # 每周推送：由GitHub Actions的cron控制运行日，这里只要有内容就发
            return len(events) > 0
        
        return True
    
    def send(self, markdown_content: str, mode: str = "daily") -> bool:
        """
        发送邮件
        
        Args:
            markdown_content: Markdown格式的简报内容
            mode: daily / major_only / weekly
            
        Returns:
            True=发送成功
        """
        recipients = self.push_config.get("email_recipients", [])
        if not recipients:
            logger.warning("邮件接收人列表为空，跳过发送")
            return False
        
        # 主题
        now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
        mode_title = {
            "daily": "每日简报",
            "major_only": "⚠️ 重大事件特报",
            "weekly": "每周汇总"
        }.get(mode, "简报")
        subject = f"[RWA创业情报] {mode_title} - {now.strftime('%Y-%m-%d')}"
        
        # 构建邮件
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_user or "rwa-briefing@noreply.local"
        msg["To"] = ", ".join(recipients)
        
        # 纯文本版本
        text_part = MIMEText(markdown_content, "plain", "utf-8")
        msg.attach(text_part)
        
        # HTML版本 (将Markdown转换为HTML)
        try:
            html_body = self._markdown_to_email_html(markdown_content)
            html_part = MIMEText(html_body, "html", "utf-8")
            msg.attach(html_part)
        except Exception as e:
            logger.warning(f"Markdown转HTML失败，仅发送纯文本: {e}")
        
        # 发送
        if not self.smtp_user or not self.smtp_password:
            # 无凭据时，保存到本地文件作为演示
            logger.warning("未配置SMTP凭据，将简报保存到本地 output/ 目录（演示模式）")
            self._save_to_local(markdown_content, subject, now)
            return True
        
        try:
            return self._send_smtp(msg, recipients)
        except Exception as e:
            logger.error(f"SMTP发送失败: {e}，保存到本地备份")
            self._save_to_local(markdown_content, subject, now)
            return False
    
    def _send_smtp(self, msg: MIMEMultipart, recipients: List[str]) -> bool:
        """
        通过SMTP真实发送邮件
        - 端口465: 使用SSL直连 (如 126/QQ/163邮箱)
        - 端口587/25: 使用STARTTLS升级 (如 Gmail)
        - 若环境有HTTP代理，自动通过代理CONNECT隧道连接
        """
        smtp_host = self.sender_config.get("smtp_host", "smtp.126.com")
        smtp_port = int(self.sender_config.get("smtp_port", 465))

        logger.info(f"正在通过 {smtp_host}:{smtp_port} 发送邮件到: {recipients}")
        context = ssl.create_default_context()

        # 尝试通过代理建立连接（沙箱/受限网络环境）
        proxy_sock = _create_proxy_socket(smtp_host, smtp_port)

        if smtp_port == 465:
            # SSL直连模式 (126/163/QQ邮箱常用)
            if proxy_sock:
                # 有代理隧道：在代理socket上包装SSL，再让smtplib在该连接上完成会话
                ssl_sock = context.wrap_socket(proxy_sock, server_hostname=smtp_host)
                # 正常初始化SMTP实例，但不连接；然后手动注入SSL socket
                server = smtplib.SMTP(timeout=30)
                server.sock = ssl_sock
                server.file = server.sock.makefile('rb')
                # 读取服务器欢迎消息并完成EHLO
                server.getreply()
                server.ehlo()
            else:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, context=context)
        else:
            # STARTTLS模式 (Gmail等)
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls(context=context)

        server.login(self.smtp_user, self.smtp_password)
        server.sendmail(self.smtp_user, recipients, msg.as_string())
        try:
            server.quit()
        except Exception:
            pass
        
        logger.info("邮件发送成功")
        return True
    
    def _save_to_local(
        self,
        markdown_content: str,
        subject: str,
        date_time: datetime
    ) -> None:
        """本地保存模式（无SMTP凭据时使用）"""
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "output"
        )
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"briefing_{date_time.strftime('%Y%m%d_%H%M')}.md"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"<!-- Subject: {subject} -->\n\n")
            f.write(markdown_content)
        
        # 同时存一份 latest.md 方便查看
        latest_path = os.path.join(output_dir, "latest.md")
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(f"<!-- Subject: {subject} -->\n\n")
            f.write(markdown_content)
        
        logger.info(f"简报已保存到本地: {filepath}")
        logger.info(f"最新简报链接: {latest_path}")
    
    def _markdown_to_email_html(self, md_content: str) -> str:
        """
        将Markdown转换为适合邮件显示的HTML
        添加一些内嵌CSS风格
        """
        html_body = markdown.markdown(
            md_content,
            extensions=["tables", "fenced_code", "nl2br"]
        )
        
        # 邮件样式模板
        email_html = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                                 "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
                                 Helvetica, Arial, sans-serif;
                    line-height: 1.7;
                    color: #24292e;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                h1 {{
                    color: #0366d6;
                    border-bottom: 2px solid #0366d6;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #24292e;
                    border-left: 4px solid #0366d6;
                    padding-left: 12px;
                    margin-top: 32px;
                }}
                h3 {{
                    color: #24292e;
                    margin-top: 24px;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 16px 0;
                }}
                th, td {{
                    border: 1px solid #dfe2e5;
                    padding: 8px 12px;
                    text-align: left;
                }}
                th {{
                    background-color: #f6f8fa;
                    font-weight: 600;
                }}
                blockquote {{
                    margin: 16px 0;
                    padding: 12px 16px;
                    background-color: #f6f8fa;
                    border-left: 4px solid #dfe2e5;
                    color: #586069;
                }}
                code {{
                    background-color: #f6f8fa;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-size: 90%;
                }}
                a {{
                    color: #0366d6;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                hr {{
                    border: 0;
                    border-top: 1px solid #eaecef;
                    margin: 24px 0;
                }}
                details {{
                    margin: 12px 0;
                    padding: 12px;
                    background: #f9fafb;
                    border-radius: 6px;
                }}
                summary {{
                    cursor: pointer;
                    font-weight: 500;
                }}
            </style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """
        return email_html
