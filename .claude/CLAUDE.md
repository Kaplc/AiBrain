## 重要提醒

1-logs\这里是放日志的目录

2-AiBrain\.port_config这个是后端的接口要测试和访问就使用这个

3-.claude\plan\这里是放项目计划的目录

4-这个是 @app.route('/overview/flask/restart', methods=['POST'])手动重启后端修改后端文件后可以使用这个接口重启后端

5-后端刚启动需要预热加载语义模型不能马上请求记忆查询和保存，可以请求一下语义模型状态的接口来确认是否预热完成
@app.route('/overview/model', methods=['GET'])

6-前端e2e测试需要使用playWright

7-前端修改完成后自动构建一下前端代码

