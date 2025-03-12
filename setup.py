from setuptools import setup, find_packages

setup(
    name='wamp_pubsub_project',
    version='1.0',
    description='Aplicación de Publicador y Suscriptor WAMP con PyQt5 y Crossbar',
    author='Enrique',
    packages=find_packages(),
    install_requires=[
        'PyQt5',
        'autobahn[asyncio]',
        'crossbar',
    ],
    entry_points={
        'console_scripts': [
            'run_wampy = main:main',
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
    ],
)
