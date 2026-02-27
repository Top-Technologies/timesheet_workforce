from odoo import api, models
import datetime
import logging

_logger = logging.getLogger(__name__)


class ReportWeeklySummary(models.AbstractModel):
    """Report parser for the consolidated weekly summary PDF."""
    _name = 'report.budget_timesheet.report_weekly_summary'
    _description = 'Weekly Summary Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        _logger.info("=== WEEKLY SUMMARY REPORT _get_report_values ===")
        _logger.info("docids: %s, data: %s", docids, data)

        # Handle empty docids (browser download flow)
        if not docids and data:
            if data.get('summary_id'):
                docids = [data['summary_id']]
            elif data.get('context', {}).get('active_ids'):
                docids = data['context']['active_ids']

        summaries = self.env['budget.timesheet.weekly.summary'].browse(docids)
        _logger.info("summaries found: %s", len(summaries))

        return {
            'doc_ids': docids,
            'doc_model': 'budget.timesheet.weekly.summary',
            'docs': summaries,
            'data': data or {},
            'datetime': datetime,
        }
