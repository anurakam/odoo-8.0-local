# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from odoo import fields
from odoo.addons.stock.tests.common2 import TestStockCommon


class TestSaleMrpLeadTime(TestStockCommon):

    def setUp(self):
        super(TestSaleMrpLeadTime, self).setUp()

        route_manufacture = self.warehouse_1.manufacture_pull_id.route_id.id
        route_mto = self.warehouse_1.mto_pull_id.route_id.id

        # Update the product_1 with type, route, Manufacturing Lead Time and Customer Lead Time
        self.product_1.write({'type': 'product',
                              'route_ids': [(6, 0, [route_manufacture, route_mto])],
                              'produce_delay': 5.0,
                              'sale_delay': 5.0})

        # Update the product_2 with type
        self.product_2.write({'type': 'consu'})

        # Create Bill of materials for product_1
        self.bom_a = self.env['mrp.bom'].create({
            'product_tmpl_id': self.product_1.product_tmpl_id.id,
            'product_qty': 2,
            'type': 'normal',
            'product_uom_id': self.uom_unit.id,
            'bom_line_ids': [(0, 0, {'product_id': self.product_2.id,
                                     'product_qty': 4,
                                     'product_uom_id': self.uom_unit.id})]})


    def test_00_product_company_level_delays(self):
        """ In order to check schedule date, set product's Manufacturing Lead Time
            and Customer Lead Time and also set company's Manufacturing Lead Time
            and Sales Safety Days."""

        company = self.env.ref('base.main_company')

        # Update company with Manufacturing Lead Time and Sales Safety Days
        company.write({'manufacturing_lead': 3.0,
                       'security_lead': 3.0})

        # Create sale order of product_1
        order = self.env['sale.order'].create({
            'partner_id': self.partner_1.id,
            'partner_invoice_id': self.partner_1.id,
            'partner_shipping_id': self.partner_1.id,
            'pricelist_id': self.env.ref('product.list0').id,
            'picking_policy': 'direct',
            'warehouse_id': self.warehouse_1.id,
            'order_line': [(0, 0, {'name': self.product_1.name,
                                   'product_id': self.product_1.id,
                                   'product_uom_qty': 10,
                                   'product_uom': self.uom_unit.id,
                                   'customer_lead': self.product_1.sale_delay})]})

        # Confirm sale order
        order.action_confirm()

        # Run scheduler
        self.env['procurement.order'].run_scheduler()

        # Check manufacturing order created or not
        manufacturing_order = self.env['procurement.order'].search([('product_id', '=', self.product_1.id), ('group_id', '=', order.procurement_group_id.id), ('production_id', '!=', False)]).production_id
        self.assertTrue(manufacturing_order, 'Manufacturing order should be created.')

        # Check the picking crated or not
        self.assertTrue(order.picking_ids, "Picking should be created.")

        # Check schedule date of picking
        out_date = fields.Datetime.from_string(order.date_order) + timedelta(days=self.product_1.sale_delay) - timedelta(days=company.security_lead)
        out_schedule_date = fields.Datetime.to_string(out_date)
        self.assertEqual(order.picking_ids[0].min_date, out_schedule_date, 'Schedule date of picking should be equal to: Order date + Customer Lead Time - Sales Safety Days.')

        # Check schedule date of manufacturing order
        mo_date = out_date - timedelta(days=self.product_1.produce_delay) - timedelta(days=company.manufacturing_lead)
        mo_schedule_date = fields.Datetime.to_string(mo_date)
        self.assertEqual(manufacturing_order.date_planned_start, mo_schedule_date, "Schedule date of manufacturing order should be equal to: Schedule date of picking - product's Manufacturing Lead Time - company's Manufacturing Lead Time.")

    def test_01_product_route_level_delays(self):
        """ In order to check schedule dates, set product's Manufacturing Lead Time
            and Customer Lead Time and also set warehouse route's delay."""

        # Update warehouse_1 with Outgoing Shippings pick + pack + ship
        self.warehouse_1.write({'delivery_steps': 'pick_pack_ship'})

        # Set delay on pull rule
        for pull_rule in self.warehouse_1.delivery_route_id.pull_ids:
            pull_rule.write({'delay': 2})

        # Create sale order of product_1
        order = self.env['sale.order'].create({
            'partner_id': self.partner_1.id,
            'partner_invoice_id': self.partner_1.id,
            'partner_shipping_id': self.partner_1.id,
            'pricelist_id': self.env.ref('product.list0').id,
            'picking_policy': 'direct',
            'warehouse_id': self.warehouse_1.id,
            'order_line': [(0, 0, {'name': self.product_1.name,
                                   'product_id': self.product_1.id,
                                   'product_uom_qty': 6,
                                   'product_uom': self.uom_unit.id,
                                   'customer_lead': self.product_1.sale_delay})]})

        # Confirm sale order
        order.action_confirm()

        # Run scheduler
        self.env['procurement.order'].run_scheduler()

        # Check manufacturing order created or not
        manufacturing_order = self.env['procurement.order'].search([('product_id', '=', self.product_1.id), ('group_id', '=', order.procurement_group_id.id), ('production_id', '!=', False)]).production_id
        self.assertTrue(manufacturing_order, 'Manufacturing order should be created.')

        # Check the picking crated or not
        self.assertTrue(order.picking_ids, "Pickings should be created.")

        # Check schedule date of ship type picking
        out = order.picking_ids.filtered(lambda r: r.picking_type_id == self.warehouse_1.out_type_id)
        out_date = fields.Datetime.from_string(order.date_order) + timedelta(days=self.product_1.sale_delay) - timedelta(days=out.move_lines[0].rule_id.delay)
        out_schedule_date = fields.Datetime.to_string(out_date)
        self.assertEqual(out.min_date, out_schedule_date, 'Schedule date of ship type picking should be equal to: order date + Customer Lead Time - pull rule delay.')

        # Check schedule date of pack type picking
        pack = order.picking_ids.filtered(lambda r: r.picking_type_id == self.warehouse_1.pack_type_id)
        pack_date = out_date - timedelta(days=pack.move_lines[0].rule_id.delay)
        pack_schedule_date = fields.Datetime.to_string(pack_date)
        self.assertEqual(pack.min_date, pack_schedule_date, 'Schedule date of pack type picking should be equal to: Schedule date of ship type picking - pull rule delay.')

        # Check schedule date of pick type picking
        pick = order.picking_ids.filtered(lambda r: r.picking_type_id == self.warehouse_1.pick_type_id)
        self.assertEqual(pick.min_date, pack_schedule_date, 'Schedule date of pick type picking should be equal to: Schedule date of pack type picking.')

        # Check schedule date of manufacturing order
        mo_date = pack_date - timedelta(days=self.product_1.produce_delay)
        mo_schedule_date = fields.Datetime.to_string(mo_date)
        self.assertEqual(manufacturing_order.date_planned_start, mo_schedule_date, "Schedule date of manufacturing order should be equal to: Schedule date of pack type picking - product's Manufacturing Lead Time.")
