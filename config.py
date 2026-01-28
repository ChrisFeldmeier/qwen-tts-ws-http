from dynaconf import Dynaconf

settings = Dynaconf(
    envvar_prefix=False,  # Load all environment variables
    settings_files=['settings.yaml', '.secrets.yaml'],
)