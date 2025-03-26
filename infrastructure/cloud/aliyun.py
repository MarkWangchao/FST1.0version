import asyncio
import logging
from typing import Optional, Callable
import oss2
from oss2.exceptions import OssError
from prometheus_client import Counter, Histogram
from tqsdk.utils import retry  # 集成天勤重试机制

# 监控指标
OSS_UPLOADS = Counter('oss_upload_ops', 'OSS上传操作总数')
OSS_FAILURES = Counter('oss_failures', 'OSS操作失败次数')
OSS_LATENCY = Histogram('oss_latency', 'OSS操作延迟分布')

class EnhancedOSSIntegration:
    """增强版阿里云OSS集成（支持量化交易需求）"""
    
    def __init__(self, config: dict):
        """
        Args:
            config: 配置字典
                - access_key: 访问密钥
                - secret_key: 私有密钥  
                - endpoint: 接入点
                - bucket_name: 存储桶名称
                - max_retries: 最大重试次数(默认3)
                - timeout: 超时时间(默认10秒)
        """
        self.config = config
        self.bucket = None
        self._session = None
        self.logger = logging.getLogger('Aliyun_OSS')
        self._init_metrics()

    def _init_metrics(self):
        """初始化监控指标"""
        self.upload_time = OSS_LATENCY.labels(operation='upload')
        self.download_time = OSS_LATENCY.labels(operation='download')

    @retry(max_retries=3, retry_exceptions=(TimeoutError,))
    async def async_connect(self):
        """异步连接初始化"""
        try:
            auth = oss2.Auth(
                self.config['access_key'],
                self.config['secret_key']
            )
            self.bucket = oss2.Bucket(
                auth,
                self.config['endpoint'],
                self.config['bucket_name'],
                connect_timeout=self.config.get('timeout', 10)
            )
            self.logger.info("OSS连接成功建立")
        except OssError as e:
            self.logger.error("OSS连接错误: %s", str(e))
            raise

    @OSS_UPLOADS.count_exceptions(OssError)
    @upload_time.time()
    async def upload_file(self, file_path: str, oss_key: str, 
                        progress_cb: Optional[Callable] = None) -> bool:
        """增强版文件上传"""
        for attempt in range(self.config.get('max_retries', 3)):
            try:
                async with await self._get_connection() as bucket:
                    result = await bucket.put_object_from_file(
                        oss_key, 
                        file_path,
                        progress_callback=progress_cb
                    )
                    if result.status == 200:
                        return True
                    raise OssError(result)
            except OssError as e:
                if e.status == 503:  # 服务不可用
                    wait = 0.5 * (2 ** attempt)
                    self.logger.warning("服务限流，等待%s秒后重试", wait)
                    await asyncio.sleep(wait)
                else:
                    OSS_FAILURES.inc()
                    raise

    async def sync_tqsdk_data(self, prefix: str):
        """同步天勤数据到OSS"""
        from tqsdk.data import get_strategy_data  # 假设天勤数据接口
        data_files = get_strategy_data()  
        for file in data_files:
            await self.upload_file(file.path, f"{prefix}/{file.name}")

# 使用示例
config = {
    "access_key": "YOUR_ACCESS_KEY",
    "secret_key": "YOUR_SECRET_KEY",
    "endpoint": "oss-cn-hangzhou.aliyuncs.com",
    "bucket_name": "quant-data",
    "max_retries": 5,
    "timeout": 15
}

async def main():
    oss = EnhancedOSSIntegration(config)
    await oss.async_connect()
    await oss.sync_tqsdk_data("tqsdk/strategies")