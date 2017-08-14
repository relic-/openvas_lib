#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This file contains OMPv7 implementation
"""

from openvas_lib import *
from openvas_lib.common import *
from openvas_lib.ompv4 import OMPv4

__license__ = """
OpenVAS connector for OMP protocol.

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

__all__ = ["OMPv7"]


# ------------------------------------------------------------------------------
#
# OMPv7 implementation
#
# ------------------------------------------------------------------------------
class OMPv7(OMPv4):
    """
    Internal manager for OpenVAS low level operations.

    ..note:
        This class is based in code from the original OpenVAS plugin:

        https://pypi.python.org/pypi/OpenVAS.omplib

    ..warning:
        This code is intended to only be compatible with OMP 7.0.
    """

    def __init__(self, omp_manager):
        """
        Constructor.

        :param omp_manager: _OMPManager object.
        :type omp_manager: ConnectionManager
        """
        super(OMPv7, self).__init__(omp_manager)

    def get_results(self, task_id=None):
        """
        Get the results associated to the scan ID.

        :param task_id: ID of scan to get. All if not provided
        :type task_id: str

        :return: xml object
        :rtype: `ElementTree`

        :raises: ClientError, ServerError
        """

        if task_id:
            m_query = '<get_results filter="task_id=%s rows=0" />' % task_id
        else:
            m_query = '<get_results/>'

        return self._manager.make_xml_request(m_query, xml_result=True)

    def resume_task(self, task_id):
        """
        Resume a stopped task.

        :param task_id: task id
        :type task_id: str

        :raises: ServerError, AuditNotFoundError
        """

        request = """<resume_task task_id="%s" />""" % task_id

        self._manager.make_xml_request(request, xml_result=True)
