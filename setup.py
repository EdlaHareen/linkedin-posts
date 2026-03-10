"""
Setup configuration for the Newsletter to LinkedIn Post Automation project.
"""

from setuptools import setup, find_packages

setup(
    name="newsletter-linkedin-automation",
    version="1.0.0",
    description="Automated backend system that converts newsletter emails into LinkedIn posts",
    author="Newsletter Automation Team",
    python_requires=">=3.9",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "Flask>=3.0.0",
        "google-auth>=2.25.0",
        "google-api-python-client>=2.110.0",
        "google-auth-oauthlib>=1.2.0",
        "google-auth-httplib2>=0.2.0",
        "openai>=1.6.0",
        "python-telegram-bot>=20.7",
        "python-dotenv>=1.0.0",
        "requests>=2.31.0",
        "python-dateutil>=2.8.2",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.3",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.12.0",
            "pytest-asyncio>=0.21.1",
            "black>=23.12.0",
            "flake8>=6.1.0",
            "mypy>=1.7.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "newsletter-automation=main:main",
        ],
    },
)
