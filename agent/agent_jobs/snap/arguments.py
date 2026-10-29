from agent._core.settings import ROOT_DIR



def get_args(service_name):
    """
    Fetches The Arguments Needed By The Program

    Returns:
        An object that has the arguments as attributes.

    Raises:s
        None
    """

    with open(ROOT_DIR / f"configs/{service_name}.yaml", 'rb') as config_file:
        import yaml
        from yaml.loader import SafeLoader
        configs = yaml.load(config_file, Loader=SafeLoader)['args']
    import argparse
    parser = argparse.ArgumentParser(description='Naji ABIS Suite Engine . . . ')
    for key in configs:
        if 'help' in configs[key] and 'type' in configs[key]:
            parser.add_argument(key, default=configs[key]['default'],
                                type=configs[key]['type'] if 'type' in configs[key] else '',
                                help=configs[key]['help'] if 'help' in configs[key] else '')
        elif 'help' in configs[key]:
            parser.add_argument(key, default=configs[key]['default'],
                                help=configs[key]['help'] if 'help' in configs[key] else '')
        elif 'type' in configs[key]:
            parser.add_argument(key, default=configs[key]['default'],
                                type=configs[key]['type'] if 'type' in configs[key] else '')
        else:
            parser.add_argument(key, default=configs[key]['default'])

    """
    We're Updating The Server Args With The Current File's Args So That It'd Get The Args It Doesn't Currently Have
    """
    from argparse import Namespace
    args_dict = vars(parser.parse_args())
    args = Namespace(**args_dict)
    return args
