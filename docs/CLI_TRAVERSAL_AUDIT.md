# 🔍 K-CLI Systematic Binary Traversal & Fuzzing Audit Report
**Total Paths Traversed**: `53` | **Passed**: `40` | **Graceful Errors**: `13` | **Crashes**: `0` | **Hangs**: `0`

## Summary Table
| Command Path | Exit Code | Duration | Status | Notes |
| :--- | :---: | :---: | :---: | :--- |
| `k-cli --help` | `0` | `1009.0ms` | 🟢 PASS | OK |
| `k-cli doctor` | `0` | `3160.5ms` | 🟢 PASS | OK |
| `k-cli status` | `0` | `1358.1ms` | 🟢 PASS | OK |
| `k-cli diff` | `0` | `1835.5ms` | 🟢 PASS | OK |
| `k-cli map` | `0` | `4616.5ms` | 🟢 PASS | OK |
| `k-cli doc json.dumps` | `0` | `1869.2ms` | 🟢 PASS | OK |
| `k-cli test` | `0` | `2266.7ms` | 🟢 PASS | OK |
| `k-cli watch --once` | `0` | `1911.1ms` | 🟢 PASS | OK |
| `k-cli bisect python -c 'import sys; sys.` | `0` | `1235.4ms` | 🟢 PASS | OK |
| `k-cli route refactor auth token verifica` | `0` | `1083.1ms` | 🟢 PASS | OK |
| `k-cli garden --json` | `0` | `2465.6ms` | 🟢 PASS | OK |
| `k-cli explain How does verifier work?` | `0` | `4536.3ms` | 🟢 PASS | OK |
| `k-cli synapse verifier AST` | `0` | `3134.2ms` | 🟢 PASS | OK |
| `k-cli airgap` | `0` | `1078.3ms` | 🟢 PASS | OK |
| `k-cli scaffold FastAPI + Redis --dir /tm` | `0` | `1072.7ms` | 🟢 PASS | OK |
| `k-cli keys` | `0` | `1235.9ms` | 🟢 PASS | OK |
| `k-cli keys test` | `0` | `1234.0ms` | 🟢 PASS | OK |
| `k-cli keys set TEST_KEY val123` | `0` | `882.1ms` | 🟢 PASS | OK |
| `k-cli auth` | `0` | `885.2ms` | 🟢 PASS | OK |
| `k-cli conflict list` | `0` | `907.2ms` | 🟢 PASS | OK |
| `k-cli conflict --help` | `0` | `986.3ms` | 🟢 PASS | OK |
| `k-cli pr list` | `0` | `1335.1ms` | 🟢 PASS | OK |
| `k-cli pr --help` | `0` | `854.1ms` | 🟢 PASS | OK |
| `k-cli gh status` | `2` | `842.1ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli gh --help` | `0` | `927.3ms` | 🟢 PASS | OK |
| `k-cli issue --help` | `0` | `962.0ms` | 🟢 PASS | OK |
| `k-cli release --help` | `0` | `985.7ms` | 🟢 PASS | OK |
| `k-cli action --help` | `0` | `979.0ms` | 🟢 PASS | OK |
| `k-cli gist --help` | `0` | `884.1ms` | 🟢 PASS | OK |
| `k-cli security scan` | `0` | `3738.3ms` | 🟢 PASS | OK |
| `k-cli models list` | `0` | `1586.6ms` | 🟢 PASS | OK |
| `k-cli mcp list` | `0` | `1448.3ms` | 🟢 PASS | OK |
| `k-cli dedup check Fix jwt auth token bug` | `0` | `6868.3ms` | 🟢 PASS | OK |
| `k-cli --invalid-flag-999` | `2` | `1670.9ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli unknown_subcommand_xyz` | `2` | `1387.4ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli explain ` | `0` | `879.8ms` | 🟢 PASS | OK |
| `k-cli explain AAAAAAAAAAAAAAAAAAAAAAAAAA` | `0` | `2645.8ms` | 🟢 PASS | OK |
| `k-cli route ` | `0` | `861.3ms` | 🟢 PASS | OK |
| `k-cli scaffold ` | `0` | `826.3ms` | 🟢 PASS | OK |
| `k-cli doc ` | `2` | `844.2ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli doc non_existent_symbol_12345` | `2` | `4570.7ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli verify --file /tmp/non_existent_fi` | `2` | `1154.8ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli keys set  ` | `1` | `1149.7ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli keys import /tmp/non_existent_file` | `1` | `1253.7ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli pr view -1` | `2` | `1504.5ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli pr review 0` | `1` | `1455.4ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli pr fix 99999` | `1` | `1865.6ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli pr merge 99999` | `1` | `1603.5ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli conflict resolve --file non_existe` | `1` | `1452.7ms` | 🟡 GRACEFUL REJECT | Handled |
| `k-cli mcp remove non_existent_server` | `0` | `1646.2ms` | 🟢 PASS | OK |
| `k-cli dedup check ` | `0` | `1574.7ms` | 🟢 PASS | OK |
| `k-cli dedup check {invalid: json, [unclo` | `0` | `7223.3ms` | 🟢 PASS | OK |
| `k-cli watch --interval 0 --once` | `0` | `2165.1ms` | 🟢 PASS | OK |