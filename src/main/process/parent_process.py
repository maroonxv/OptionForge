"""
parent_process.py - 守护进程实现

职责:
1. 启动并监控工作子进程
2. 子进程异常退出时自动重启
3. 收集子进程日志和状态
4. 处理信号量实现优雅退出

重启策略:
- 最大重启次数: 10 次
- 重启间隔: 指数退避 (5s, 10s, 20s, ...)
- 连续成功运行 1 小时后重置重启计数
"""
import sys
import time
import signal
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from src.main.config.config_loader import ConfigLoader
from src.main.utils.signal_handler import register_shutdown_signals


@dataclass
class RestartPolicy:
    """重启策略配置"""
    max_restarts: int = 10
    base_delay: float = 5.0
    max_delay: float = 300.0
    reset_after_hours: float = 1.0


class ParentProcess:
    """
    守护进程
    
    负责监控和管理工作子进程，确保策略持续运行。
    
    Attributes:
        config_path: 策略配置文件路径
        log_level: 日志级别
        log_dir: 日志目录
    """
    
    def __init__(
        self,
        config_path: str,
        override_config_path: Optional[str] = None,
        log_level: str = "INFO",
        log_dir: str = "logs/runner",
        log_name: str = "runner"
    ) -> None:
        """
        初始化守护进程
        
        Args:
            config_path: 策略配置文件路径
            override_config_path: 覆盖配置文件路径
            log_level: 日志级别
            log_dir: 日志目录
            log_name: 日志文件名
        """
        self.config_path = config_path
        self.override_config_path = override_config_path
        self.log_level = log_level
        self.log_dir = log_dir
        self.log_name = log_name
        
        self.logger = logging.getLogger(__name__)
        
        # 重启策略
        self.restart_policy = RestartPolicy()
        
        # 加载配置 (交易时段 + 重启策略覆盖)
        self.trading_periods = []
        self._load_runtime_config()
        
        # 子进程管理
        self.child_process: Optional[subprocess.Popen] = None
        self.child_pid: Optional[int] = None
        
        # 运行状态
        self.restart_count: int = 0
        self.last_start_time: Optional[datetime] = None
        self.running: bool = False
        self.shutdown_requested: bool = False
        
        # 设置信号处理
        self._setup_signal_handlers()

    def _load_runtime_config(self) -> None:
        """加载运行时配置"""
        try:
            # 加载基础配置
            config = ConfigLoader.load_toml(self.config_path)
            
            # 如果有覆盖配置，进行合并
            if self.override_config_path:
                override_config = ConfigLoader.load_toml(self.override_config_path)
                # 注意：ConfigLoader.merge_strategy_config 主要合并 strategies 字段
                # 如果 runtime 配置也在 override 中，我们需要手动合并 runtime 部分，
                # 或者假设 merge_strategy_config 也能处理（目前看代码它只处理了 strategies）。
                # 这里假设 runtime 配置主要在 base config 中，
                # 但为了支持 override 中覆盖 runtime 配置，我们做一个简单的字典更新。
                if "runtime" in override_config:
                    if "runtime" not in config:
                        config["runtime"] = {}
                    config["runtime"].update(override_config["runtime"])
            
            runtime_config = config.get("runtime", {})
            
            # 加载交易时段
            self.trading_periods = runtime_config.get("trading_periods", [])
            
            # 加载重启策略
            if "max_restart_count" in runtime_config:
                self.restart_policy.max_restarts = int(runtime_config["max_restart_count"])
            
            if "restart_delay" in runtime_config:
                self.restart_policy.base_delay = float(runtime_config["restart_delay"])
                
            self.logger.info(
                f"运行时配置已加载: "
                f"max_restarts={self.restart_policy.max_restarts}, "
                f"base_delay={self.restart_policy.base_delay}, "
                f"periods={len(self.trading_periods)}"
            )

        except Exception as e:
            self.logger.warning(f"加载运行时配置失败: {e}，将使用默认配置")
            self.trading_periods = []

    def _is_trading_period(self) -> bool:
        """
        检查当前是否在交易时段
        
        如果没有配置时段，默认返回 True (全天运行)
        """
        if not self.trading_periods:
            return True
            
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        for period in self.trading_periods:
            start = period["start"]
            end = period["end"]
            
            if start <= end:
                # 同一日内 (e.g. 09:00 - 15:00)
                if start <= current_time <= end:
                    return True
            else:
                # 跨日 (e.g. 21:00 - 02:30)
                if current_time >= start or current_time <= end:
                    return True
                    
        return False
    
    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        # 使用共享模块注册 SIGTERM 和 SIGINT
        register_shutdown_signals(self._handle_shutdown_signal)
        
        # Windows 不支持 SIGHUP，需要单独处理 reload 信号
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, self._handle_reload_signal)
    
    def _handle_shutdown_signal(self, signum: int, frame) -> None:
        """
        处理关闭信号
        
        Args:
            signum: 信号编号
            frame: 当前栈帧
        """
        self.logger.info(f"收到关闭信号 {signum}")
        self.shutdown_requested = True
    
    def _handle_reload_signal(self, signum: int, frame) -> None:
        """
        处理重载信号 (SIGHUP)
        
        触发子进程重启以重新加载配置
        
        Args:
            signum: 信号编号
            frame: 当前栈帧
        """
        self.logger.info("收到重载信号，准备重启子进程")
        self._stop_child()
        # 不用调用 start_child，run 循环会自动重启
    
    def run(self) -> None:
        """
        运行守护进程主循环
        """
        self.running = True
        self.logger.info("守护进程启动")
        
        while self.running and not self.shutdown_requested:
            # 检查交易时段
            if self._is_trading_period():
                # --- 交易时段逻辑 ---
                if self.child_process is None or self.child_process.poll() is not None:
                    if not self._should_restart():
                        self.logger.error("达到最大重启次数，守护进程退出")
                        break
                    
                    self._start_child()
                
                # 等待子进程状态变化
                try:
                    if self.child_process:
                        return_code = self.child_process.wait(timeout=1.0)
                        self._handle_child_exit(return_code)
                except subprocess.TimeoutExpired:
                    # 子进程仍在运行
                    self._check_reset_restart_count()
                except Exception as e:
                    self.logger.error(f"监控子进程异常: {e}")
                    time.sleep(1.0)
            else:
                # --- 非交易时段逻辑 ---
                if self.child_process is not None:
                    self.logger.info("进入非交易时段，停止子进程...")
                    self._stop_child()
                    # 重置重启计数，确保下个交易时段能正常启动
                    self.restart_count = 0
                
                # 休眠等待 (避免空转)
                time.sleep(30.0)
        
        self.graceful_shutdown()
    
    def _start_child(self) -> None:
        """
        启动工作子进程
        
        使用 subprocess.Popen 启动 child_process.py
        """
        delay = self._calculate_restart_delay()
        if delay > 0:
            self.logger.info(f"等待 {delay:.1f} 秒后重启...")
            time.sleep(delay)
        
        self.restart_count += 1
        self.last_start_time = datetime.now()
        
        # 构建子进程命令 - 指向新位置 src/main/process/child_process.py
        child_script = Path(__file__).parent / "child_process.py"
        
        cmd = [
            sys.executable,
            str(child_script),
            "--config", self.config_path,
            "--log-level", self.log_level,
            "--log-dir", self.log_dir,
            "--log-name", self.log_name
        ]
        
        if self.override_config_path:
            cmd.extend(["--override-config", self.override_config_path])
        
        self.logger.info(f"启动子进程 (第 {self.restart_count} 次)")
        
        try:
            # Windows 下不使用 close_fds=True，或者仔细测试
            # 这里简单起见，标准输出继承到父进程，方便调试
            self.child_process = subprocess.Popen(
                cmd,
                # stdout=subprocess.PIPE,
                # stderr=subprocess.STDOUT,
                # text=True
                # 如果希望在父进程看到子进程输出，可以不重定向，或者重定向到日志文件
                # 设计文档中是 PIPE，这里为了简单直接输出到控制台/父进程日志
            )
            self.child_pid = self.child_process.pid
            self.logger.info(f"子进程已启动, PID: {self.child_pid}")
            
        except Exception as e:
            self.logger.error(f"启动子进程失败: {e}")
            self.child_process = None
    
    def _stop_child(self) -> None:
        """停止子进程"""
        if self.child_process is None:
            return
        
        self.logger.info("正在停止子进程...")
        
        try:
            # 1. 优先等待子进程自行退出 (因为 Ctrl+C 会同时发给子进程)
            # 给它 5 秒钟的时间处理保存逻辑
            try:
                self.child_process.wait(timeout=5.0)
                self.logger.info("子进程已自行退出")
                return
            except subprocess.TimeoutExpired:
                pass

            # 2. 如果没退出，发送 SIGTERM
            self.logger.info("子进程未退出，发送终止信号...")
            self.child_process.terminate()
            
            # 3. 再次等待
            try:
                self.child_process.wait(timeout=10.0)
                self.logger.info("子进程已响应终止信号并退出")
            except subprocess.TimeoutExpired:
                # 4. 强制杀进程
                self.logger.warning("子进程未响应，强制终止")
                self.child_process.kill()
                self.child_process.wait()
                
        except Exception as e:
            self.logger.error(f"停止子进程异常: {e}")
        finally:
            self.child_process = None
            self.child_pid = None
    
    def _handle_child_exit(self, return_code: int) -> None:
        """
        处理子进程退出
        
        Args:
            return_code: 子进程退出码
        """
        if return_code == 0:
            self.logger.info("子进程正常退出")
        else:
            self.logger.warning(f"子进程异常退出, 返回码: {return_code}")
        
        self.child_process = None
        self.child_pid = None
    
    def _should_restart(self) -> bool:
        """
        判断是否应该重启
        
        Returns:
            True 如果应该重启
        """
        if self.shutdown_requested:
            return False
        
        if self.restart_count >= self.restart_policy.max_restarts:
            return False
        
        return True
    
    def _calculate_restart_delay(self) -> float:
        """
        计算重启延迟时间 (指数退避)
        
        Returns:
            延迟秒数
        """
        if self.restart_count == 0:
            return 0
        
        delay = self.restart_policy.base_delay * (2 ** (self.restart_count - 1))
        return min(delay, self.restart_policy.max_delay)
    
    def _check_reset_restart_count(self) -> None:
        """检查是否应该重置重启计数"""
        if self.last_start_time is None:
            return
        
        elapsed = datetime.now() - self.last_start_time
        reset_threshold = timedelta(hours=self.restart_policy.reset_after_hours)
        
        if elapsed > reset_threshold and self.restart_count > 0:
            self.logger.info("子进程运行稳定，重置重启计数")
            self.restart_count = 0
    
    def graceful_shutdown(self) -> None:
        """优雅关闭"""
        self.logger.info("守护进程开始关闭...")
        self.running = False
        self._stop_child()
        self.logger.info("守护进程已关闭")
