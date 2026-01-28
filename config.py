from dynaconf import Dynaconf
import os
import logging

current_directory = os.path.dirname(os.path.realpath(__file__))
settings = Dynaconf(
    root_path=current_directory,
    envvar_prefix=False,  # Load all environment variables
    settings_files=['settings.yaml', '.secrets.yaml'],
    merge_enabled=True
)

# Configure logging
log_level = settings.get('logging.level', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("qwen-tts")