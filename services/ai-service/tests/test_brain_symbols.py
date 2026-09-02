from app.brain.symbols import extract_symbols, guess_language


def test_guess_language_from_extension():
    assert guess_language("app/main.py") == "python"
    assert guess_language("src/index.ts") == "typescript"
    assert guess_language("src/App.tsx") == "typescript"
    assert guess_language("lib/utils.js") == "javascript"
    assert guess_language("README.md") == "markdown"


def test_guess_language_returns_none_for_unrecognized_extension():
    assert guess_language("data.bin") is None
    assert guess_language("Makefile") is None


def test_extract_python_symbols_finds_functions_and_classes_with_real_line_numbers():
    content = (
        "def top_level():\n"
        "    pass\n"
        "\n"
        "\n"
        "class Widget:\n"
        "    def render(self):\n"
        "        return None\n"
        "\n"
        "    async def async_render(self):\n"
        "        return None\n"
    )
    symbols = extract_symbols("app.py", content)

    by_name = {s.name: s for s in symbols}
    assert by_name["top_level"].kind == "function"
    assert by_name["top_level"].start_line == 1
    assert by_name["top_level"].end_line == 2

    assert by_name["Widget"].kind == "class"
    assert by_name["Widget"].start_line == 5

    assert by_name["render"].kind == "function"
    assert by_name["async_render"].kind == "function"
    assert {s.name for s in symbols} == {"top_level", "Widget", "render", "async_render"}


def test_extract_python_symbols_returns_empty_on_a_syntax_error_instead_of_crashing():
    assert extract_symbols("broken.py", "def broken(:\n    pass\n") == []


def test_extract_python_symbols_returns_empty_for_a_file_with_no_functions_or_classes():
    assert extract_symbols("data.py", "X = 1\nY = 2\n") == []


def test_extract_js_symbols_finds_function_declarations():
    content = "function greet(name) {\n  return `hi ${name}`;\n}\n"
    symbols = extract_symbols("app.js", content)
    assert len(symbols) == 1
    assert symbols[0].name == "greet"
    assert symbols[0].kind == "function"
    assert symbols[0].start_line == 1
    assert symbols[0].end_line is None


def test_extract_ts_symbols_finds_exported_classes_and_arrow_const_functions():
    content = (
        "export class UserService {\n"
        "  constructor() {}\n"
        "}\n"
        "\n"
        "export const formatDate = (d: Date) => {\n"
        "  return d.toISOString();\n"
        "};\n"
    )
    symbols = extract_symbols("service.ts", content)
    names = {(s.name, s.kind) for s in symbols}
    assert ("UserService", "class") in names
    assert ("formatDate", "function") in names


def test_extract_symbols_returns_empty_for_an_unrecognized_language():
    assert extract_symbols("README.md", "# Title\n\nSome content.\n") == []
