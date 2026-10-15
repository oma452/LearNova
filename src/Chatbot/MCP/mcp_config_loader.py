import json
from pathlib import Path
from typing import Dict, Any
from functools import lru_cache

from src.Helpers.config import get_settings, Settings


class MCPConfigLoader:
    """
    Handles the loading and processing of the mcp_config.json file.
    
    - Reads the JSON configuration.
    - Resolves environment variable placeholders (e.g., ${VAR_NAME})
      using the central Settings object.
    - Resolves relative file paths for local python servers.
    """
    def __init__(self, settings: Settings, config_path: Path):
        self.settings = settings
        self.config_path = config_path
        
        if not self.config_path.exists():
            raise FileNotFoundError(f"MCP config file not found at {self.config_path}")

        self.project_root = self._get_project_root()
        self._raw_config = self._load_raw_config()
        self.processed_config = self._process_config()

    def _get_project_root(self) -> Path:
        """Finds the project root by looking for the '.env' file or 'pyproject.toml'."""
        current_path = Path(__file__).resolve()
        for parent in current_path.parents:
            if (parent / ".env").exists() or (parent / "pyproject.toml").exists():
                return parent
        raise FileNotFoundError("Could not determine project root.")

    def _load_raw_config(self) -> Dict[str, Any]:
        """Loads the raw JSON config from the file."""
        with open(self.config_path, "r") as f:
            return json.load(f)
            
    def _process_config(self) -> Dict[str, Any]:
        """Orchestrates the processing of the configuration."""
        # Work on a deep copy to avoid modifying the original dict in memory
        config_copy = json.loads(json.dumps(self._raw_config))
        
        config_with_env = self._resolve_env_vars(config_copy)
        final_config = self._resolve_relative_paths(config_with_env)
        
        return final_config

    def _resolve_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Replaces ${VAR} placeholders using values from the Settings object."""
        skipped_servers = []
        
        for server_name, server_config in list(config.get("mcpServers", {}).items()):
            # Process 'env' dictionary
            if "env" in server_config:
                for key, value in server_config["env"].items():
                    if isinstance(value, str) and value.startswith("${"):
                        env_var_name = value[2:-1]
                        # Use getattr to dynamically get the setting
                        env_var_value = getattr(self.settings, env_var_name, None)
                        if env_var_value:
                            server_config["env"][key] = env_var_value
                        else:
                            print(f"Warning: Env var '{env_var_name}' not set. Skipping server '{server_name}'.")
                            skipped_servers.append(server_name)
                            break # No need to check other vars for this server
            
            if server_name in skipped_servers: continue

            # Process 'args' list
            if "args" in server_config:
                for i, arg in enumerate(server_config["args"]):
                    if isinstance(arg, str) and arg.startswith("${"):
                        env_var_name = arg[2:-1]
                        env_var_value = getattr(self.settings, env_var_name, None)
                        if env_var_value:
                            server_config["args"][i] = env_var_value
                        else:
                            print(f"Warning: Env var '{env_var_name}' not set. Skipping server '{server_name}'.")
                            skipped_servers.append(server_name)
                            break
        
        # Remove skipped servers from the configuration
        for server_name in set(skipped_servers):
            if server_name in config["mcpServers"]:
                del config["mcpServers"][server_name]

        return config
        
    def _resolve_relative_paths(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Resolves relative script paths in 'args' to absolute paths."""
        for server_name, server_config in config.get("mcpServers", {}).items():
            if "args" in server_config:
                for i, arg in enumerate(server_config["args"]):
                    # Check if it looks like a relative path to a Python script
                    if isinstance(arg, str) and arg.endswith(".py") and not Path(arg).is_absolute():
                        absolute_path = (self.project_root / arg).resolve()
                        if absolute_path.exists():
                            server_config["args"][i] = str(absolute_path)
                        else:
                            print(f"Warning: Server file not found at resolved path: {absolute_path}")
        return config


@lru_cache()
def get_mcp_config() -> Dict[str, Any]:
    """
    Returns a single, processed instance of the MCP configuration.
    
    The function is cached, so the file reading and processing only happens
    on the very first call. All subsequent calls return the cached result.
    """
    print("Loading and processing MCP configuration for the first time...")
    settings = get_settings()
    # The config file is in the same directory as this loader.
    config_path = Path(__file__).parent / "mcp_config.json"
    
    loader = MCPConfigLoader(settings=settings, config_path=config_path)
    return loader.processed_config