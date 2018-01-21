#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from asyncio import get_event_loop

from aiohttp import ClientSession
from tornado.httpserver import HTTPServer
from tornado.platform.asyncio import AsyncIOMainLoop
from tornado.web import Application
from tornado.web import RequestHandler

import instana.instrumentation.instrument_tornado


class MainHandler(RequestHandler):

	def post(self):
		self.write("Hello Post")

	def head(self):
		self.write("Hello Head")

	async def get(self):
		clientSession = ClientSession()
		async with clientSession as client:
			async with client.get('http://status.instana.io', timeout=None) as response:
				self.write(await response.text())


if __name__ == '__main__':
	AsyncIOMainLoop().install()
	app = Application([
		(r'/', MainHandler),
	])
	server = HTTPServer(app)
	port = 9999
	server.listen(port)
	print("Server starting on " + str(port))

	get_event_loop().run_forever()