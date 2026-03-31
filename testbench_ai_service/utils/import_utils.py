import importlib

from testbench_ai_service.log import logger


def load_class_from_path(class_path: str):
    """
    Dynamically load and return a class using its dotted import path.

    Args:
        class_path (str): Class import path in the format 'module.submodule.ClassName'.

    Raises:
        ImportError: If the module or class cannot be imported or found.

    Returns:
        type: The class object specified by the path.
    """
    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name, None)
    if cls is None:
        logger.error(f"Class '{class_name}' not found in '{module_path}'")
        raise ImportError(f"Class '{class_name}' not found in '{module_path}'")
    return cls
