#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 文件操作工具

提供文件和目录操作的工具函数，包括：
- 文件读写
- 路径处理
- 文件类型检查
- 文件搜索
- 配置文件处理
- 数据文件处理
- 文件压缩与解压

File utilities for FST framework:
- File reading and writing
- Path manipulation
- File type checking
- File searching
- Config file handling
- Data file handling
- File compression and extraction
"""

import os
import sys
import shutil
import glob
import json
import yaml
import csv
import tempfile
import zipfile
import gzip
import bz2
import logging
import hashlib
import pathlib
from typing import Any, Dict, List, Optional, Set, Tuple, Union, Callable, BinaryIO, TextIO

# 日志配置
logger = logging.getLogger("fst.utils.file")


def ensure_directory(directory_path: str) -> bool:
    """
    确保目录存在，如果不存在则创建
    
    Args:
        directory_path: 目录路径
    
    Returns:
        bool: 创建成功或已存在返回True，否则返回False
    """
    try:
        if not os.path.exists(directory_path):
            os.makedirs(directory_path, exist_ok=True)
            logger.debug(f"创建目录: {directory_path}")
        return True
    except Exception as e:
        logger.error(f"创建目录失败 {directory_path}: {str(e)}")
        return False


def delete_directory(directory_path: str, recursive: bool = True) -> bool:
    """
    删除目录
    
    Args:
        directory_path: 目录路径
        recursive: 是否递归删除
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        if os.path.exists(directory_path):
            if recursive:
                shutil.rmtree(directory_path)
                logger.debug(f"递归删除目录: {directory_path}")
            else:
                os.rmdir(directory_path)
                logger.debug(f"删除空目录: {directory_path}")
        return True
    except Exception as e:
        logger.error(f"删除目录失败 {directory_path}: {str(e)}")
        return False


def ensure_parent_directory(file_path: str) -> bool:
    """
    确保文件的父目录存在
    
    Args:
        file_path: 文件路径
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        parent_dir = os.path.dirname(file_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
            logger.debug(f"创建父目录: {parent_dir}")
        return True
    except Exception as e:
        logger.error(f"创建父目录失败 {os.path.dirname(file_path)}: {str(e)}")
        return False


def read_text_file(file_path: str, encoding: str = 'utf-8') -> Optional[str]:
    """
    读取文本文件内容
    
    Args:
        file_path: 文件路径
        encoding: 文件编码
    
    Returns:
        str: 文件内容，出错时返回None
    """
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
        return content
    except Exception as e:
        logger.error(f"读取文件失败 {file_path}: {str(e)}")
        return None


def read_text_file_lines(file_path: str, encoding: str = 'utf-8') -> Optional[List[str]]:
    """
    读取文本文件行
    
    Args:
        file_path: 文件路径
        encoding: 文件编码
    
    Returns:
        List[str]: 文件行列表，出错时返回None
    """
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            lines = [line.rstrip('\n') for line in f]
        return lines
    except Exception as e:
        logger.error(f"读取文件行失败 {file_path}: {str(e)}")
        return None


def write_text_file(file_path: str, content: str, encoding: str = 'utf-8') -> bool:
    """
    写入文本文件
    
    Args:
        file_path: 文件路径
        content: 文件内容
        encoding: 文件编码
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        ensure_parent_directory(file_path)
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"写入文件失败 {file_path}: {str(e)}")
        return False


def append_text_file(file_path: str, content: str, encoding: str = 'utf-8') -> bool:
    """
    追加文本文件
    
    Args:
        file_path: 文件路径
        content: 要追加的内容
        encoding: 文件编码
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        ensure_parent_directory(file_path)
        with open(file_path, 'a', encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"追加文件失败 {file_path}: {str(e)}")
        return False


def read_binary_file(file_path: str) -> Optional[bytes]:
    """
    读取二进制文件
    
    Args:
        file_path: 文件路径
    
    Returns:
        bytes: 文件内容，出错时返回None
    """
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        return content
    except Exception as e:
        logger.error(f"读取二进制文件失败 {file_path}: {str(e)}")
        return None


def write_binary_file(file_path: str, content: bytes) -> bool:
    """
    写入二进制文件
    
    Args:
        file_path: 文件路径
        content: 二进制内容
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        ensure_parent_directory(file_path)
        with open(file_path, 'wb') as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"写入二进制文件失败 {file_path}: {str(e)}")
        return False


def delete_file(file_path: str) -> bool:
    """
    删除文件
    
    Args:
        file_path: 文件路径
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"删除文件: {file_path}")
        return True
    except Exception as e:
        logger.error(f"删除文件失败 {file_path}: {str(e)}")
        return False


def copy_file(source_path: str, target_path: str, overwrite: bool = True) -> bool:
    """
    复制文件
    
    Args:
        source_path: 源文件路径
        target_path: 目标文件路径
        overwrite: 是否覆盖已存在的文件
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        if not os.path.exists(source_path):
            logger.error(f"源文件不存在: {source_path}")
            return False
            
        if os.path.exists(target_path) and not overwrite:
            logger.warning(f"目标文件已存在且不允许覆盖: {target_path}")
            return False
        
        ensure_parent_directory(target_path)
        shutil.copy2(source_path, target_path)
        logger.debug(f"复制文件: {source_path} -> {target_path}")
        return True
    except Exception as e:
        logger.error(f"复制文件失败 {source_path} -> {target_path}: {str(e)}")
        return False


def move_file(source_path: str, target_path: str, overwrite: bool = True) -> bool:
    """
    移动文件
    
    Args:
        source_path: 源文件路径
        target_path: 目标文件路径
        overwrite: 是否覆盖已存在的文件
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        if not os.path.exists(source_path):
            logger.error(f"源文件不存在: {source_path}")
            return False
            
        if os.path.exists(target_path) and not overwrite:
            logger.warning(f"目标文件已存在且不允许覆盖: {target_path}")
            return False
        
        ensure_parent_directory(target_path)
        shutil.move(source_path, target_path)
        logger.debug(f"移动文件: {source_path} -> {target_path}")
        return True
    except Exception as e:
        logger.error(f"移动文件失败 {source_path} -> {target_path}: {str(e)}")
        return False


def copy_directory(source_dir: str, target_dir: str, overwrite: bool = True) -> bool:
    """
    复制目录
    
    Args:
        source_dir: 源目录路径
        target_dir: 目标目录路径
        overwrite: 是否覆盖已存在的目录
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        if not os.path.exists(source_dir):
            logger.error(f"源目录不存在: {source_dir}")
            return False
            
        if os.path.exists(target_dir) and not overwrite:
            logger.warning(f"目标目录已存在且不允许覆盖: {target_dir}")
            return False
        elif os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        
        shutil.copytree(source_dir, target_dir)
        logger.debug(f"复制目录: {source_dir} -> {target_dir}")
        return True
    except Exception as e:
        logger.error(f"复制目录失败 {source_dir} -> {target_dir}: {str(e)}")
        return False


def get_file_size(file_path: str) -> Optional[int]:
    """
    获取文件大小（字节）
    
    Args:
        file_path: 文件路径
    
    Returns:
        int: 文件大小（字节），出错时返回None
    """
    try:
        if os.path.exists(file_path):
            return os.path.getsize(file_path)
        else:
            logger.warning(f"文件不存在: {file_path}")
            return None
    except Exception as e:
        logger.error(f"获取文件大小失败 {file_path}: {str(e)}")
        return None


def get_file_mtime(file_path: str) -> Optional[float]:
    """
    获取文件修改时间戳
    
    Args:
        file_path: 文件路径
    
    Returns:
        float: 文件修改时间戳，出错时返回None
    """
    try:
        if os.path.exists(file_path):
            return os.path.getmtime(file_path)
        else:
            logger.warning(f"文件不存在: {file_path}")
            return None
    except Exception as e:
        logger.error(f"获取文件修改时间失败 {file_path}: {str(e)}")
        return None


def get_file_extension(file_path: str) -> str:
    """
    获取文件扩展名（小写）
    
    Args:
        file_path: 文件路径
    
    Returns:
        str: 文件扩展名（不包含点，小写），无扩展名时返回空字符串
    """
    _, ext = os.path.splitext(file_path)
    return ext.lower()[1:] if ext else ""


def is_file_extension(file_path: str, extensions: Union[str, List[str]]) -> bool:
    """
    判断文件是否具有指定扩展名
    
    Args:
        file_path: 文件路径
        extensions: 扩展名或扩展名列表（不含点）
    
    Returns:
        bool: 是否具有指定扩展名
    """
    if isinstance(extensions, str):
        extensions = [extensions]
        
    file_ext = get_file_extension(file_path)
    return file_ext.lower() in [ext.lower() for ext in extensions]


def list_files(
    directory: str, 
    pattern: str = "*", 
    recursive: bool = False, 
    include_dirs: bool = False
) -> List[str]:
    """
    列出目录中的文件
    
    Args:
        directory: 目录路径
        pattern: 通配符模式，如"*.txt"
        recursive: 是否递归处理子目录
        include_dirs: 是否包含目录
    
    Returns:
        List[str]: 文件路径列表
    """
    try:
        if not os.path.exists(directory):
            logger.warning(f"目录不存在: {directory}")
            return []
            
        glob_pattern = os.path.join(directory, pattern)
        
        if recursive:
            glob_pattern = os.path.join(directory, "**", pattern)
            files = glob.glob(glob_pattern, recursive=True)
        else:
            files = glob.glob(glob_pattern)
        
        # 过滤目录
        if not include_dirs:
            files = [f for f in files if os.path.isfile(f)]
            
        return files
    except Exception as e:
        logger.error(f"列出文件失败 {directory}: {str(e)}")
        return []


def list_directories(directory: str, pattern: str = "*", recursive: bool = False) -> List[str]:
    """
    列出目录中的子目录
    
    Args:
        directory: 目录路径
        pattern: 通配符模式，如"data*"
        recursive: 是否递归处理子目录
    
    Returns:
        List[str]: 子目录路径列表
    """
    try:
        if not os.path.exists(directory):
            logger.warning(f"目录不存在: {directory}")
            return []
            
        glob_pattern = os.path.join(directory, pattern)
        
        if recursive:
            glob_pattern = os.path.join(directory, "**", pattern)
            all_items = glob.glob(glob_pattern, recursive=True)
        else:
            all_items = glob.glob(glob_pattern)
        
        # 仅包含目录
        directories = [d for d in all_items if os.path.isdir(d)]
            
        return directories
    except Exception as e:
        logger.error(f"列出目录失败 {directory}: {str(e)}")
        return []


def normalize_path(path: str) -> str:
    """
    标准化路径（处理相对路径，路径分隔符等）
    
    Args:
        path: 路径
    
    Returns:
        str: 标准化后的路径
    """
    return os.path.normpath(os.path.abspath(path))


def make_relative_path(path: str, base_dir: str) -> str:
    """
    创建相对于给定目录的相对路径
    
    Args:
        path: 要转换的路径
        base_dir: 基准目录
    
    Returns:
        str: 相对路径
    """
    abs_path = os.path.abspath(path)
    abs_base = os.path.abspath(base_dir)
    
    try:
        rel_path = os.path.relpath(abs_path, abs_base)
    except ValueError:
        # 如果在不同驱动器上（Windows），则返回原始路径
        rel_path = abs_path
        
    return rel_path


def join_path(*paths: str) -> str:
    """
    连接路径
    
    Args:
        *paths: 路径片段
    
    Returns:
        str: 连接后的路径
    """
    return os.path.join(*paths)


def get_filename(file_path: str, with_extension: bool = True) -> str:
    """
    获取文件名
    
    Args:
        file_path: 文件路径
        with_extension: 是否包含扩展名
    
    Returns:
        str: 文件名
    """
    if with_extension:
        return os.path.basename(file_path)
    else:
        return os.path.splitext(os.path.basename(file_path))[0]


def get_directory_name(path: str) -> str:
    """
    获取目录名
    
    Args:
        path: 路径
    
    Returns:
        str: 目录名
    """
    return os.path.basename(os.path.normpath(path))


def is_subpath(path: str, base_path: str) -> bool:
    """
    判断路径是否为另一路径的子路径
    
    Args:
        path: 要检查的路径
        base_path: 基准路径
    
    Returns:
        bool: 是否为子路径
    """
    abs_path = os.path.abspath(path)
    abs_base = os.path.abspath(base_path)
    
    # 考虑Windows和Unix路径格式
    norm_path = os.path.normcase(abs_path)
    norm_base = os.path.normcase(abs_base)
    
    return norm_path.startswith(norm_base)


def read_json_file(file_path: str, encoding: str = 'utf-8') -> Optional[Dict[str, Any]]:
    """
    读取JSON文件
    
    Args:
        file_path: 文件路径
        encoding: 文件编码
    
    Returns:
        Dict[str, Any]: JSON数据，出错时返回None
    """
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取JSON文件失败 {file_path}: {str(e)}")
        return None


def write_json_file(
    file_path: str, 
    data: Dict[str, Any], 
    encoding: str = 'utf-8', 
    indent: int = 4,
    ensure_ascii: bool = False
) -> bool:
    """
    写入JSON文件
    
    Args:
        file_path: 文件路径
        data: JSON数据
        encoding: 文件编码
        indent: 缩进空格数
        ensure_ascii: 是否确保ASCII输出
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        ensure_parent_directory(file_path)
        with open(file_path, 'w', encoding=encoding) as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        return True
    except Exception as e:
        logger.error(f"写入JSON文件失败 {file_path}: {str(e)}")
        return False


def read_yaml_file(file_path: str, encoding: str = 'utf-8') -> Optional[Dict[str, Any]]:
    """
    读取YAML文件
    
    Args:
        file_path: 文件路径
        encoding: 文件编码
    
    Returns:
        Dict[str, Any]: YAML数据，出错时返回None
    """
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"读取YAML文件失败 {file_path}: {str(e)}")
        return None


def write_yaml_file(
    file_path: str, 
    data: Dict[str, Any], 
    encoding: str = 'utf-8'
) -> bool:
    """
    写入YAML文件
    
    Args:
        file_path: 文件路径
        data: YAML数据
        encoding: 文件编码
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        ensure_parent_directory(file_path)
        with open(file_path, 'w', encoding=encoding) as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        return True
    except Exception as e:
        logger.error(f"写入YAML文件失败 {file_path}: {str(e)}")
        return False


def read_csv_file(
    file_path: str, 
    encoding: str = 'utf-8',
    delimiter: str = ',',
    has_header: bool = True
) -> Optional[List[Dict[str, str]]]:
    """
    读取CSV文件
    
    Args:
        file_path: 文件路径
        encoding: 文件编码
        delimiter: 分隔符
        has_header: 是否有标题行
    
    Returns:
        List[Dict[str, str]]: CSV数据列表，出错时返回None
    """
    try:
        result = []
        with open(file_path, 'r', encoding=encoding, newline='') as f:
            if has_header:
                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    result.append(dict(row))
            else:
                reader = csv.reader(f, delimiter=delimiter)
                header = [f"col{i}" for i in range(len(next(reader)))]
                result.append(dict(zip(header, reader[0])))
                for row in reader:
                    result.append(dict(zip(header, row)))
        return result
    except Exception as e:
        logger.error(f"读取CSV文件失败 {file_path}: {str(e)}")
        return None


def write_csv_file(
    file_path: str,
    data: List[Dict[str, Any]],
    fieldnames: Optional[List[str]] = None,
    encoding: str = 'utf-8',
    delimiter: str = ','
) -> bool:
    """
    写入CSV文件
    
    Args:
        file_path: 文件路径
        data: 数据列表
        fieldnames: 列名列表，默认使用第一行的键
        encoding: 文件编码
        delimiter: 分隔符
        
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        ensure_parent_directory(file_path)
        
        if not data:
            logger.warning(f"CSV数据为空: {file_path}")
            return False
            
        if fieldnames is None:
            fieldnames = list(data[0].keys())
            
        with open(file_path, 'w', encoding=encoding, newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(data)
            
        return True
    except Exception as e:
        logger.error(f"写入CSV文件失败 {file_path}: {str(e)}")
        return False


def create_zip_file(
    zip_file_path: str, 
    files_to_add: List[str], 
    base_dir: Optional[str] = None,
    compression: int = zipfile.ZIP_DEFLATED
) -> bool:
    """
    创建ZIP文件
    
    Args:
        zip_file_path: ZIP文件路径
        files_to_add: 要添加的文件路径列表
        base_dir: 基准目录，用于计算相对路径
        compression: 压缩方法
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        ensure_parent_directory(zip_file_path)
        
        with zipfile.ZipFile(zip_file_path, 'w', compression=compression) as zip_file:
            for file_path in files_to_add:
                if not os.path.exists(file_path):
                    logger.warning(f"文件不存在，跳过: {file_path}")
                    continue
                    
                if base_dir:
                    arcname = make_relative_path(file_path, base_dir)
                else:
                    arcname = os.path.basename(file_path)
                    
                zip_file.write(file_path, arcname)
                
        return True
    except Exception as e:
        logger.error(f"创建ZIP文件失败 {zip_file_path}: {str(e)}")
        return False


def extract_zip_file(
    zip_file_path: str, 
    extract_dir: str,
    members: Optional[List[str]] = None
) -> bool:
    """
    解压ZIP文件
    
    Args:
        zip_file_path: ZIP文件路径
        extract_dir: 解压目录
        members: 要解压的文件列表，None表示全部解压
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        if not os.path.exists(zip_file_path):
            logger.error(f"ZIP文件不存在: {zip_file_path}")
            return False
            
        ensure_directory(extract_dir)
        
        with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
            zip_file.extractall(extract_dir, members=members)
            
        return True
    except Exception as e:
        logger.error(f"解压ZIP文件失败 {zip_file_path}: {str(e)}")
        return False


def list_zip_contents(zip_file_path: str) -> Optional[List[str]]:
    """
    列出ZIP文件内容
    
    Args:
        zip_file_path: ZIP文件路径
        
    Returns:
        List[str]: 文件名列表，出错时返回None
    """
    try:
        if not os.path.exists(zip_file_path):
            logger.error(f"ZIP文件不存在: {zip_file_path}")
            return None
            
        with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
            return zip_file.namelist()
    except Exception as e:
        logger.error(f"列出ZIP文件内容失败 {zip_file_path}: {str(e)}")
        return None


def compress_file(file_path: str, compression: str = 'gzip') -> Optional[str]:
    """
    压缩单个文件
    
    Args:
        file_path: 要压缩的文件路径
        compression: 压缩方法，'gzip'或'bz2'
    
    Returns:
        str: 压缩后的文件路径，出错时返回None
    """
    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        return None
        
    try:
        if compression.lower() == 'gzip':
            out_path = f"{file_path}.gz"
            with open(file_path, 'rb') as f_in:
                with gzip.open(out_path, 'wb') as f_out:
                    f_out.writelines(f_in)
        elif compression.lower() == 'bz2':
            out_path = f"{file_path}.bz2"
            with open(file_path, 'rb') as f_in:
                with bz2.open(out_path, 'wb') as f_out:
                    f_out.writelines(f_in)
        else:
            logger.error(f"不支持的压缩方法: {compression}")
            return None
            
        return out_path
    except Exception as e:
        logger.error(f"压缩文件失败 {file_path}: {str(e)}")
        return None


def decompress_file(file_path: str) -> Optional[str]:
    """
    解压单个文件
    
    Args:
        file_path: 要解压的文件路径
    
    Returns:
        str: 解压后的文件路径，出错时返回None
    """
    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        return None
        
    try:
        if file_path.endswith('.gz'):
            out_path = file_path[:-3]  # 去掉.gz后缀
            with gzip.open(file_path, 'rb') as f_in:
                with open(out_path, 'wb') as f_out:
                    f_out.writelines(f_in)
        elif file_path.endswith('.bz2'):
            out_path = file_path[:-4]  # 去掉.bz2后缀
            with bz2.open(file_path, 'rb') as f_in:
                with open(out_path, 'wb') as f_out:
                    f_out.writelines(f_in)
        else:
            logger.error(f"不支持的压缩格式: {file_path}")
            return None
            
        return out_path
    except Exception as e:
        logger.error(f"解压文件失败 {file_path}: {str(e)}")
        return None


def calculate_file_md5(file_path: str, block_size: int = 8192) -> Optional[str]:
    """
    计算文件MD5哈希值
    
    Args:
        file_path: 文件路径
        block_size: 读取块大小
    
    Returns:
        str: MD5哈希值（16进制字符串），出错时返回None
    """
    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        return None
        
    try:
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(block_size), b''):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception as e:
        logger.error(f"计算文件MD5失败 {file_path}: {str(e)}")
        return None


def calculate_file_sha256(file_path: str, block_size: int = 8192) -> Optional[str]:
    """
    计算文件SHA256哈希值
    
    Args:
        file_path: 文件路径
        block_size: 读取块大小
    
    Returns:
        str: SHA256哈希值（16进制字符串），出错时返回None
    """
    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        return None
        
    try:
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(block_size), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logger.error(f"计算文件SHA256失败 {file_path}: {str(e)}")
        return None


def get_temp_file(suffix: str = '', prefix: str = 'fst_', dir: Optional[str] = None) -> str:
    """
    获取临时文件路径
    
    Args:
        suffix: 文件后缀
        prefix: 文件前缀
        dir: 临时文件目录
    
    Returns:
        str: 临时文件路径
    """
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir)
    os.close(fd)  # 关闭文件描述符
    return path


def get_temp_dir(suffix: str = '', prefix: str = 'fst_', dir: Optional[str] = None) -> str:
    """
    获取临时目录路径
    
    Args:
        suffix: 目录后缀
        prefix: 目录前缀
        dir: 临时目录的父目录
    
    Returns:
        str: 临时目录路径
    """
    return tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)


def find_files_by_content(
    directory: str, 
    search_text: str, 
    pattern: str = "*",
    recursive: bool = True,
    case_sensitive: bool = False
) -> List[str]:
    """
    按内容搜索文件
    
    Args:
        directory: 目录路径
        search_text: 搜索文本
        pattern: 文件模式，如"*.py"
        recursive: 是否递归搜索
        case_sensitive: 是否区分大小写
    
    Returns:
        List[str]: 匹配的文件路径列表
    """
    if not os.path.exists(directory):
        logger.warning(f"目录不存在: {directory}")
        return []
        
    files = list_files(directory, pattern, recursive)
    result = []
    
    if not case_sensitive:
        search_text = search_text.lower()
        
    for file_path in files:
        try:
            with open(file_path, 'r', errors='ignore') as f:
                content = f.read()
                
            if not case_sensitive:
                content = content.lower()
                
            if search_text in content:
                result.append(file_path)
        except Exception as e:
            logger.debug(f"搜索文件内容失败 {file_path}: {str(e)}")
            continue
            
    return result


def create_symlink(source_path: str, link_path: str, overwrite: bool = True) -> bool:
    """
    创建符号链接
    
    Args:
        source_path: 源路径
        link_path: 链接路径
        overwrite: 是否覆盖已存在的链接
    
    Returns:
        bool: 操作成功返回True，否则返回False
    """
    try:
        if os.path.lexists(link_path) and overwrite:
            os.remove(link_path)
        elif os.path.lexists(link_path):
            logger.warning(f"链接已存在且不允许覆盖: {link_path}")
            return False
            
        ensure_parent_directory(link_path)
        
        # 使用相对路径或绝对路径
        os.symlink(source_path, link_path)
        logger.debug(f"创建符号链接: {source_path} -> {link_path}")
        return True
    except Exception as e:
        logger.error(f"创建符号链接失败 {source_path} -> {link_path}: {str(e)}")
        return False