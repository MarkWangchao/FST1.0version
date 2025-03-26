import asyncio
import logging
from typing import Optional
import boto3
from botocore.exceptions import (
    NoCredentialsError,
    PartialCredentialsError,
    ClientError,
    ConnectTimeoutError
)
from prometheus_client import Counter, Histogram
from tqsdk.utils import retry  # 集成天勤重试机制

# 监控指标
S3_UPLOADS = Counter('s3_upload_ops', 'Total S3 upload operations')
S3_FAILURES = Counter('s3_failures', 'S3 operation failures')
S3_LATENCY = Histogram('s3_latency', 'S3 operation latency')

class EnhancedAWSIntegration:
    """增强版AWS S3集成（支持量化交易系统需求）"""
    
    def __init__(self, config: dict):
        """
        Args:
            config: 包含AWS凭证和配置的字典
                - access_key: AWS访问密钥
                - secret_key: AWS密钥
                - region_name: 区域 (默认"us-west-1")
                - max_retries: 最大重试次数 (默认3)
                - timeout: 超时时间秒数 (默认10)
        """
        self.config = config
        self.s3_client = None
        self._session = None
        self.logger = logging.getLogger('AWS_S3')
        self._init_metrics()

    def _init_metrics(self):
        """初始化Prometheus监控指标"""
        self.upload_time = S3_LATENCY.labels(operation='upload')
        self.download_time = S3_LATENCY.labels(operation='download')

    @retry(max_retries=3, retry_exceptions=(TimeoutError,))  # 使用天勤重试装饰器
    async def async_connect(self):
        """异步连接初始化"""
        try:
            self._session = boto3.Session(
                aws_access_key_id=self.config['access_key'],
                aws_secret_access_key=self.config['secret_key'],
                region_name=self.config.get('region_name', 'us-west-1')
            )
            self.s3_client = self._session.client(
                's3',
                config=botocore.config.Config(
                    connect_timeout=self.config.get('timeout', 10),
                    retries={'max_attempts': self.config.get('max_retries', 3)}
                )
            )
            self.logger.info("Successfully connected to AWS S3 with latency %sms", latency)
        except (NoCredentialsError, PartialCredentialsError) as e:
            self.logger.error("Credential error: %s", str(e))
            raise
        except ConnectTimeoutError as e:
            self.logger.warning("Connection timeout, retrying...")
            raise TimeoutError(str(e))

    @S3_UPLOADS.count_exceptions(ClientError)
    @upload_time.time()
    async def upload_file(self, file_path: str, bucket: str, key: str) -> bool:
        """增强版文件上传（含重试机制）"""
        for attempt in range(self.config.get('max_retries', 3)):
            try:
                with open(file_path, 'rb') as f:
                    await self.s3_client.upload_fileobj(
                        f, bucket, key,
                        Callback=self._progress_callback
                    )
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == 'SlowDown':
                    wait = 0.5 * (2 ** attempt)
                    self.logger.info("Throttling detected, waiting %ss", wait)
                    await asyncio.sleep(wait)
                else:
                    S3_FAILURES.inc()
                    raise

    def _progress_callback(self, bytes_transferred):
        """上传进度回调（可用于GUI更新）"""
        self.logger.debug("Transferred %s bytes", bytes_transferred)

    async def sync_tqsdk_logs(self, bucket: str, prefix: str):
        """同步天勤量化日志到S3"""
        from tqsdk.logger import get_log_files  # 假设天勤有日志接口
        log_files = get_log_files()
        for log_file in log_files:
            await self.upload_file(log_file, bucket, f"{prefix}/{log_file.name}")

# 使用示例
config = {
    "access_key": "YOUR_ACCESS_KEY",
    "secret_key": "YOUR_SECRET_KEY",
    "region_name": "us-west-2",
    "max_retries": 5,
    "timeout": 15
}

async def main():
    s3 = EnhancedAWSIntegration(config)
    await s3.async_connect()
    await s3.sync_tqsdk_logs("quant-logs", "tqsdk/daily")