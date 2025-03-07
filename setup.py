
from setuptools import setup, find_packages

setup(
    name="fst",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "tqsdk>=2.0.0",
        "numpy>=1.20.0",
        "pandas>=1.3.0",
        "matplotlib>=3.5.0",
        "PyYAML>=6.0",
        "SQLAlchemy>=1.4.0",
    ],
    author="FST Team",
    author_email="example@example.com",
    description="FST (Full Self Trading) - 量化交易系统",
    keywords="trading, quant, strategy",
    python_requires=">=3.8",
)
