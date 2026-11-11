"""Guide available image operations in the accepted run."""

ALIAS = '__studio_image_recipes__'


def compose(config):
    rights = config.get('permissions', {})
    instructions = []
    if config.get('engine', {}).get('kind') == 'studio':
        target = config.get('imageGenerationTarget', {})
        if config.get('imageGenerationEnabled') and rights.get('studio.generate_image'):
            if target.get('available'):
                instructions.append('Use studio_generate_image for requested assets. For edits, reference the saved image or accepted attachment IDs. Preserve transparency unless the user requests a change.')
            else:
                instructions.append('Image generation requires an available image connection.')
    elif config.get('nativeImageGeneration') is True:
        instructions.append('Use the declared native image tool for requested assets. Use verified image references for edits and preserve transparency unless requested otherwise.')
    if rights.get('studio.list_generated_images'):
        instructions.append('Use studio_list_generated_images for saved image IDs. Show images with their returned presentation.markdown. Base visual claims on pixels the model received.')
    if config.get('owner', {}).get('type') == 'project' and rights.get('studio.import_generated_image') and rights.get('studio.write_file'):
        instructions.append('Import the selected image into Assets. Register ICON or RESOURCE in module.R4MF as needed, and verify the build resourceInventory. Preserve project pins and existing resource names.')
        if rights.get('studio.read_file'):
            instructions.append('For implementation examples, read the SDK companion index ' + ALIAS + '/README.txt.')
    if not instructions:
        return ''
    return '\n\nCURRENT STUDIO IMAGE CONTRACT: ' + ' '.join(instructions)
