import unittest

from app.api_spec import load_api_spec_html, render_markdown_document


class ApiSpecHtmlTests(unittest.TestCase):
    def test_render_markdown_document_handles_headings_lists_tables_and_code(self):
        markdown = """# Title

本文の `inline` 例です。  
2行目です。

- top
  - child

| Name | Value |
| --- | --- |
| foo | `bar` |

```json
{"ok": true}
```
"""

        html = render_markdown_document(markdown)

        self.assertIn('<h1 id="title">Title</h1>', html)
        self.assertIn("<p>本文の <code>inline</code> 例です。<br>2行目です。</p>", html)
        self.assertIn('<li class="md-depth-0">top</li>', html)
        self.assertIn('<li class="md-depth-1">child</li>', html)
        self.assertIn("<thead><tr><th>Name</th><th>Value</th></tr></thead>", html)
        self.assertIn("<td><code>bar</code></td>", html)
        self.assertIn('<pre><code class="language-json">{&quot;ok&quot;: true}</code></pre>', html)

    def test_load_api_spec_html_renders_current_markdown_spec(self):
        html = load_api_spec_html()

        self.assertIn("Journal RAG API 仕様書", html)
        self.assertIn("<table>", html)
        self.assertIn("/api/account-classifications", html)
        self.assertIn("<code>application/json</code>", html)


if __name__ == "__main__":
    unittest.main()
