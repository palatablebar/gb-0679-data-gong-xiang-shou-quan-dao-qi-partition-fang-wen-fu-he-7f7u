# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV；列差异解释不完整的批次封存暂停，导出返回409。运行结果带compat块：接收决策、原列与新增列依据、逐列差异解释；parameters.column_explanations可补充解释使封存恢复。
