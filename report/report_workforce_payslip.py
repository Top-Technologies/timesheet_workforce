from odoo import api, models
import datetime
import logging

_logger = logging.getLogger(__name__)


class ReportWorkforcePayslip(models.AbstractModel):
    """Custom report parser for workforce payslip PDF."""
    _name = 'report.budget_timesheet.report_workforce_payslip'
    _description = 'Workforce Payslip Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        _logger.info("=== PAYSLIP REPORT _get_report_values called ===")
        _logger.info("docids: %s, data keys: %s", docids, list((data or {}).keys()))

        # When called from the browser download flow, docids may be empty.
        # Fall back to entry_id from data, or active_ids from context.
        if not docids and data:
            if data.get('entry_id'):
                docids = [data['entry_id']]
                _logger.info("Using entry_id from data: %s", docids)
            elif data.get('context', {}).get('active_ids'):
                docids = data['context']['active_ids']
                _logger.info("Using active_ids from context: %s", docids)

        entries = self.env['budget.timesheet.entry'].browse(docids)
        _logger.info("entries found: %s (ids=%s)", len(entries), entries.ids)

        # Filter lines by date range if wizard data is provided
        filtered_data = {}
        for entry in entries:
            if data and data.get('line_ids'):
                lines = self.env['budget.timesheet.entry.line'].browse(
                    data['line_ids']
                ).exists()
                _logger.info("Using wizard line_ids: %s lines", len(lines))
            else:
                lines = entry.line_ids
                _logger.info("Using all entry lines: %s lines", len(lines))

            filtered_data[entry.id] = {
                'lines': lines.sorted('date'),
                'total_hours': sum(lines.mapped('unit_hours')),
                'total_amount': sum(lines.mapped('amount')),
            }

        result = {
            'doc_ids': docids,
            'doc_model': 'budget.timesheet.entry',
            'docs': entries,
            'data': data or {},
            'filtered_data': filtered_data,
            'datetime': datetime,
        }
        _logger.info("=== Returning report values, docs count: %s ===", len(entries))
        return result
