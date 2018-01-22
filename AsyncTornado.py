from __future__ import print_function
from asyncio import get_event_loop
from aiohttp import ClientSession
from tornado.httpserver import HTTPServer
from tornado.platform.asyncio import AsyncIOMainLoop
from tornado.web import Application
from tornado.web import RequestHandler
import opentracing.ext.tags as ext
import opentracing as ot
import instana
import opentracing
import wrapt

instana.service_name = "Tornado Async 🌪"


@wrapt.patch_function_wrapper('aiohttp', 'client.ClientSession.get')
def urlopen_with_instana(wrapped, instance, args, kwargs):
	print("Instrumenting aiohttp")
	context = instana.internal_tracer.current_context()

	# If we're not tracing, just return
	if context is None:
		return wrapped(*args, **kwargs)

	try:
		span = instana.internal_tracer.start_span("aiohttp", child_of=context)
		span.set_tag(ext.HTTP_URL, args[1])
		span.set_tag(ext.HTTP_METHOD, args[0])

		instana.internal_tracer.inject(span.context, opentracing.Format.HTTP_HEADERS, kwargs["headers"])
		rv = wrapped(*args, **kwargs)

		span.set_tag(ext.HTTP_STATUS_CODE, rv.status)
		if 500 <= rv.status <= 599:
			span.set_tag("error", True)
			ec = span.tags.get('ec', 0)
			span.set_tag("ec", ec + 1)

	except Exception as e:
		span.log_kv({'message': e})
		span.set_tag("error", True)
		ec = span.tags.get('ec', 0)
		span.set_tag("ec", ec + 1)
		span.finish()
		raise
	else:
		span.finish()
		return rv


instana.log.debug("Instrumenting aiohttp")


@wrapt.patch_function_wrapper('tornado.web', '_HandlerDelegate.execute')
def wrapRequestHandler(wrapped, instance, args, kwargs):
	try:
		print(instance.request)
		print(args)
		span = opentracing.tracer.start_span(operation_name="tornade-request 🌪")
		span.set_tag(ext.COMPONENT, "RequestHandler")
		span.set_tag(ext.SPAN_KIND, "tornado-request-handler")
		span.set_tag(ext.SPAN_KIND, ext.SPAN_KIND_RPC_SERVER)
		span.set_tag(ext.PEER_HOSTNAME, instance.request.host)
		span.set_tag(ext.HTTP_URL, instance.request.uri)
		span.set_tag(ext.HTTP_METHOD, instance.request.method)
		rv = wrapped(*args, **kwargs)
	except Exception as e:
		span.log_kv({'message': e})
		span.set_tag("error", True)
		ec = span.tags.get('ec', 0)
		span.set_tag("ec", ec + 1)
		span.finish()
		raise
	else:
		span.set_tag(ext.HTTP_STATUS_CODE, 200)
		span.finish()
		return rv


def __call__(self, request):
	env = request.environ
	if 'HTTP_X_INSTANA_T' in env and 'HTTP_X_INSTANA_S' in env:
		ctx = ot.global_tracer.extract(ot.Format.HTTP_HEADERS, env)
		span = ot.global_tracer.start_span("tornado", child_of=ctx)
	else:
		span = ot.global_tracer.start_span("tornado")

	span.set_tag(ext.HTTP_URL, env['PATH_INFO'])
	span.set_tag("http.params", env['QUERY_STRING'])
	span.set_tag(ext.HTTP_METHOD, request.method)
	span.set_tag("http.host", env['HTTP_HOST'])
	response = self.get_response(request)

	if 500 <= response.status_code <= 511:
		span.set_tag("error", True)
		ec = span.tags.get('ec', 0)
		span.set_tag("ec", ec + 1)

	span.set_tag(ext.HTTP_STATUS_CODE, response.status_code)
	ot.global_tracer.inject(span.context, ot.Format.HTTP_HEADERS, response)
	span.finish()
	return response


instana.log.debug("Instrumenting tornado")


class MainHandler(RequestHandler):

	async def get(self):
		applicationSession = ClientSession()
		self.write("Starting")
		async with applicationSession as client:
			async with client.get('http://status.instana.io', timeout=None) as response:
				self.write(await response.text())
		applicationSession.close()

class BasicHandler(RequestHandler):

	async def get(self):
		self.write("Starting")
		results = await getWebPage()
		self.write(results)


async def getWebPage() :
	results = ""
	applicationSession = ClientSession()
	async with applicationSession as client:
		async with client.get('http://status.instana.io', timeout=None) as response:
			results = await response.text()
	client.close()
	return results


class ServiceHandler(RequestHandler):

	def prepare(self):
		self.applicationSession = ClientSession()
		pass

	async def get(self):
		self.write("Starting")
		async with self.applicationSession as client:
			async with client.get('http://status.instana.io', timeout=None) as response:
				self.write(await response.text())

	def on_finish(self):
		self.applicationSession.close()
		pass



if __name__ == '__main__':
	port = 8887
	print("Starting Async Server on " + str(port))
	AsyncIOMainLoop().install()
	app = Application([
		(r'/', MainHandler),
		(r'/main', MainHandler),
		(r'/basic', BasicHandler),
		(r'/service', ServiceHandler),

	])
	server = HTTPServer(app)
	server.listen(port)
	get_event_loop().run_forever()