我会把“一键回归”落到工作区常用位置：优先放在 .vscode/tasks.json（便于你在 VS Code 直接运行），并补一个 scripts 下的可复用脚本。先检查当前是否已有这些文件以避免覆盖。

Searched for files matching tasks.json and Makefile
我将新增两个文件：一个放在 .vscode 作为可视化任务入口，另一个放在 scripts 作为命令行复用入口，这样两种使用方式都可用。

Created run_regression.sh
Created tasks.json

Ran chmod +x /Users/home/workspace/nesthub/scripts/run...
已写好，放在合适的位置并验证可用。

新增文件

run_regression.sh
tasks.json
我还做了验证

已赋予脚本执行权限并执行一次。
结果：6 passed（14.90s）。
你现在可以这样用

VS Code 中运行任务：选择任务 regression: focused runtime。
终端直接运行：run_regression.sh。