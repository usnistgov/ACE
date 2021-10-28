from ace.streamproxy import StreamingProxy


svc = StreamingProxy("AnalyticFilter", analytic_addr="object_detector:50051")
svc.Run()