from app.tools.risk_rules import find_block_reason


def test_blocks_rm_rf_root():
    assert find_block_reason("rm -rf /") is not None


def test_blocks_rm_rf_root_wildcard():
    assert find_block_reason("rm -rf /*") is not None


def test_blocks_rm_fr_flag_order():
    assert find_block_reason("rm -fr /") is not None


def test_blocks_rm_with_long_flags():
    assert find_block_reason("rm --recursive --force /") is not None


def test_blocks_rm_no_preserve_root():
    assert find_block_reason("rm -rf --no-preserve-root /") is not None


def test_blocks_format_drive():
    assert find_block_reason("format C:") is not None
    assert find_block_reason("FORMAT d:") is not None


def test_blocks_rd_recursive_quiet_drive_root():
    assert find_block_reason("rd /s /q C:\\") is not None


def test_blocks_remove_item_recurse_force_drive_root():
    assert find_block_reason("Remove-Item -Recurse -Force C:\\") is not None


def test_blocks_dd_over_disk_device():
    assert find_block_reason("dd if=/dev/zero of=/dev/sda") is not None


def test_blocks_mkfs_on_disk_device():
    assert find_block_reason("mkfs.ext4 /dev/sda1") is not None


def test_does_not_block_ordinary_commands():
    assert find_block_reason("pytest -q") is None
    assert find_block_reason("npm test") is None
    assert find_block_reason("git status") is None
    assert find_block_reason("ls -la") is None


def test_does_not_block_rm_of_a_specific_file_or_folder():
    # The whole point: rm -rf of a *real, specific* path is exactly what a coding agent
    # legitimately does (e.g. cleaning up a build directory) — only root-like targets block.
    assert find_block_reason("rm -rf node_modules") is None
    assert find_block_reason("rm -rf ./dist") is None
    assert find_block_reason("rm -rf D:/kirxil-cli-verify") is None


def test_does_not_block_drop_database_the_prd_keeps_this_at_require_confirmation():
    # PRD §11's own example: DROP DATABASE production is REQUIRE CONFIRMATION, not BLOCK — that's
    # the existing HIGH-risk approval pause (host.run_command's risk_level), not this module.
    assert find_block_reason("psql -c 'DROP DATABASE production'") is None


def test_does_not_block_format_as_a_substring_of_something_else():
    assert find_block_reason("npm run format") is None
    assert find_block_reason("cargo fmt") is None
