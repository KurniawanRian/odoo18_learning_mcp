# -*- coding: utf-8 -*-
# from odoo import http


# class McpSaleOrder(http.Controller):
#     @http.route('/mcp_sale_order/mcp_sale_order', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/mcp_sale_order/mcp_sale_order/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('mcp_sale_order.listing', {
#             'root': '/mcp_sale_order/mcp_sale_order',
#             'objects': http.request.env['mcp_sale_order.mcp_sale_order'].search([]),
#         })

#     @http.route('/mcp_sale_order/mcp_sale_order/objects/<model("mcp_sale_order.mcp_sale_order"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('mcp_sale_order.object', {
#             'object': obj
#         })

