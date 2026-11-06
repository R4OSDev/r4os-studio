"""One bounded standalone Images response through the shared HTTP child."""
import codecs
from model_transport import ModelTransport,ModelFault,loads,dumps

class ImageDecoder:
    def __init__(self):self.decoder=codecs.getincrementaldecoder('utf-8')('strict');self.parts=[];self.size=0
    def push(self,chunk,final=False):
        self.size+=len(chunk)
        if self.size>24*1024*1024:raise ModelFault('image_response_limit')
        try:self.parts.append(self.decoder.decode(chunk,final))
        except UnicodeError:raise ModelFault('image_response_invalid') from None
        return [''.join(self.parts)] if final else []

class ImageResponse:
    def __init__(self):self.value=None;self.origin=None;self.usage=None
    def push(self,raw):
        if self.value is not None:raise ModelFault('image_response_invalid')
        value=loads(raw)
        if (not isinstance(value,dict) or type(value.get('created')) is not int or value['created']<0
                or not isinstance(value.get('data'),list) or len(value['data'])!=1
                or not isinstance(value['data'][0],dict) or not isinstance(value['data'][0].get('b64_json'),str)
                or not 0<len(value['data'][0]['b64_json'])<=4*((16*1024*1024+2)//3)
                or value.get('usage') is not None and not isinstance(value['usage'],dict)):
            raise ModelFault('image_response_invalid')
        self.value=value;self.usage=value.get('usage')
        self.origin={'imageGenerationId':value['data'][0].get('generation_id'),'reportedModel':value.get('model')}
    def result(self):
        if self.value is None:raise ModelFault('image_response_incomplete')
        return {'content':[],'imageResponse':self.value,'origin':self.origin,'usage':self.usage,'finishReason':'completed'}

class ImageTransport(ModelTransport):
    def decoder(self):return ImageDecoder()
    def prepare(self,payload,instructions,tools,effort=''):
        if (instructions or tools or effort or self.binding.get('imageAction') not in ('generate','edit')
                or payload.get('model')!=self.binding['model'] or len(dumps(payload).encode())>8*1024*1024):
            raise ModelFault('image_request_invalid',not_dispatched=True)
        return payload,ImageResponse()
