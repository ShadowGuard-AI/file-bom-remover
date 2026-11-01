import argparse
import logging
import os
import pathlib
import codecs
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define BOM encodings
# Only these three encodings exist here. UTF-32 is absent, and that
# matters: the UTF-16 LE mark is the first two bytes of the UTF-32 LE
# mark, so a UTF-32 file processed as utf-16le loses two bytes and is
# corrupt afterwards. The encoding is the caller's declaration, never
# detected from the file.
BOM_ENCODINGS = {
    'utf-8': codecs.BOM_UTF8,
    'utf-16le': codecs.BOM_UTF16_LE,
    'utf-16be': codecs.BOM_UTF16_BE,
}


def remove_bom(file_path, encoding):
    """
    Removes the Byte Order Mark (BOM) from a file.

    Args:
        file_path (str): The path to the file.
        encoding (str): The encoding of the file (e.g., 'utf-8', 'utf-16le', 'utf-16be').

    Returns:
        bool: True if BOM was removed, False otherwise.  Returns None if error.
    """
    try:
        with open(file_path, 'rb') as f:
            content = f.read()

        bom = BOM_ENCODINGS.get(encoding)
        if bom is None:
            logging.error(f"Unsupported encoding: {encoding}")
            return None  # Indicate an error

        # Everything is bytes. The file is read whole, checked for the declared
        # encoding's mark at offset zero, and rewritten in place with the mark
        # sliced off. There is no backup copy, so a write that fails halfway
        # leaves a truncated file. Files are small text files in practice, but
        # the risk is part of the design and worth saying out loud.
        if content.startswith(bom):
            logging.info(f"BOM found in {file_path} ({encoding})")
            new_content = content[len(bom):]

            with open(file_path, 'wb') as f:
                f.write(new_content)
            logging.info(f"BOM removed from {file_path}")
            return True
        else:
            logging.debug(f"No BOM found in {file_path} ({encoding})")
            return False  # No BOM found
    except Exception as e:
        logging.error(f"Error processing {file_path}: {e}")
        return None  # Indicate an error


# remove_bom returns a three way result: True removed, False no mark,
# None error. This wrapper flattens it into (removed, errors) counts so
# the directory walk and main can both work in totals.
def process_file(file_path, encoding):
    try:
        result = remove_bom(file_path, encoding)
        if result is None:
            logging.error(f"Failed to process {file_path} (see previous errors).")
            return (0, 1)
        return (1 if result else 0, 0)
    except Exception as e:
        logging.error(f"Unexpected error processing {file_path}: {e}")
        return (0, 1)


def process_directory(directory, encoding, recursive):
    """
    Processes a directory to remove BOMs from files within it.

    Args:
        directory (str): The path to the directory.
        encoding (str): The encoding to use.
        recursive (bool): Whether to process subdirectories recursively.
    """
    removed = 0
    errors = 0
    try:
        # listdir order is filesystem order, not sorted. Processing order does
        # not affect the totals, but log lines from two runs over the same
        # directory can appear in different orders.
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isfile(item_path):
                r, e = process_file(item_path, encoding)
                removed += r; errors += e
            elif os.path.isdir(item_path) and recursive:
                r, e = process_directory(item_path, encoding, recursive)
                removed += r; errors += e
            elif os.path.isdir(item_path) and not recursive:
                logging.info(f"Skipping subdirectory {item_path} (recursive is False).")
    except OSError as e:
        logging.error(f"Error accessing directory {directory}: {e}")
        errors += 1
    except Exception as e:
        logging.error(f"Unexpected error processing directory {directory}: {e}")
        errors += 1
    return (removed, errors)


def setup_argparse():
    """
    Sets up the command-line argument parser.

    Returns:
        argparse.ArgumentParser: The argument parser.
    """
    parser = argparse.ArgumentParser(description='Detects and removes Byte Order Marks (BOMs) from text-based files.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-f', '--file', help='Path to a single file.')
    group.add_argument('-d', '--directory', help='Path to a directory to process.')
    parser.add_argument('-e', '--encoding', default='utf-8', choices=['utf-8', 'utf-16le', 'utf-16be'],
                        help='Encoding to use (default: utf-8).')
    parser.add_argument('-r', '--recursive', action='store_true',
                        help='Recursively process subdirectories (only valid with -d).')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging (DEBUG level).')
    return parser


def main():
    """
    Main function to parse arguments and process files/directories.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled.")

    if args.file:
        file_path = args.file
        if not os.path.isfile(file_path):
            logging.error(f"File not found: {file_path}")
            print(f"Error: file not found: {file_path}")
            return 1
        removed, errors = process_file(file_path, args.encoding)
    elif args.directory:
        directory_path = args.directory
        if not os.path.isdir(directory_path):
            logging.error(f"Directory not found: {directory_path}")
            print(f"Error: directory not found: {directory_path}")
            return 1
        removed, errors = process_directory(directory_path, args.encoding, args.recursive)
    else:
        return 1
    print(f"BOMs removed: {removed}")
    logging.info(f"BOMs removed: {removed}")
    if errors:
        print(f"Error: {errors} file(s) could not be processed.")
        return 1
    # Removing nothing is a failure exit, even when nothing errored. A
    # caller scripting around this tool asked for a mark to be gone, and an
    # untouched file should not read as success.
    if removed == 0:
        print("Nothing removed: no byte order mark was found.")
        return 1
    return 0


if __name__ == "__main__":
    # Usage examples (not executed when running the script directly, but helpful for understanding)
    # To run from command line:
    # python main.py -f myfile.txt -e utf-8
    # python main.py -d mydirectory -e utf-16le -r
    # python main.py -d mydirectory -e utf-8
    sys.exit(main())