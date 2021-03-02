import grpc

import org_pb2
import org_pb2_grpc


with grpc.insecure_channel('localhost:8002') as channel:
    stub = org_pb2_grpc.OrgControllerStub(channel)
    response = stub.List(org_pb2.OrgListRequest(user_email="matheus.soares@ilhasoft.com.br"))
    for data in response:
        # print(data)
        print(data.id)
        print(data.name)
        print(data.uuid)
