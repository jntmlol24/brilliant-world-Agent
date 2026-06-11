"""Proto 生成的 Python 模块包。

生产环境应使用 protoc 重新生成::

    protoc --python_out=src/bw_vector_sync/proto_gen \\
           -I proto proto/dual_write_event.proto

本目录当前包含一份兼容 API 的手写实现（见 dual_write_event_pb2.py），
开发与单元测试可直接使用，序列化采用 JSON over bytes（可读、跨语言易调试）。
"""
