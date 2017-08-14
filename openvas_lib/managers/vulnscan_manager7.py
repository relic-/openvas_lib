from collections import Iterable
import re

from openvas_lib import VulnscanManager
from openvas_lib.data import *
from openvas_lib.utils import *
from openvas_lib.common import *

try:
    from xml.etree import cElementTree as etree
except ImportError:
    from xml.etree import ElementTree as etree


def results_parser(results, ignore_log_info=True):
    """
    This functions transform etree result objects to OpenVASResult object structure.

    Language specification: http://docs.greenbone.net/API/OMP/omp-7.0.html

    :param results: Scan results
    :type results: ElementTree Element

    :param ignore_log_info: Ignore Threats with Log and Debug info
    :type ignore_log_info: bool

    :raises: etree.ParseError

    :return: list of OpenVASResult structures.
    :rtype: list(OpenVASResult)
    """
    if not etree.iselement(results):
        raise TypeError("Expected Element, got '%s' instead" % type(results))

    # Regex
    port_regex_specific = re.compile("([\w\d\s]*)\(([\d]+)/([\w\W\d]+)\)")
    port_regex_generic = re.compile("([\w\d\s]*)/([\w\W\d]+)")
    cvss_regex = re.compile("(cvss_base_vector=[\s]*)([\w:/]+)")
    vulnerability_IDs = ("cve", "bid", "bugtraq")

    m_return = []
    m_return_append = m_return.append

    # All the results
    for l_results in results.findall("result"):
        l_partial_result = OpenVASResult()

        # Id
        l_vid = None
        try:
            l_vid = l_results.get("id")
            l_partial_result.id = l_vid
        except TypeError as e:
            logging.warning("%s is not a valid vulnerability ID, skipping vulnerability..." % l_vid)
            logging.debug(e)
            continue

        # --------------------------------------------------------------------------
        # Filter invalid vulnerability
        # --------------------------------------------------------------------------
        threat = l_results.find("threat")
        if threat is None:
            logging.warning("Vulnerability %s can't has 'None' as thread value, skipping vulnerability..." % l_vid)
            continue
        else:
            # Valid threat?
            if threat.text not in OpenVASResult.risk_levels:
                logging.warning("%s is not a valid risk level for %s vulnerability. skipping vulnerability..."
                                % (threat.text,
                                   l_vid))
                continue

        # Ignore log/debug messages, only get the results
        if threat.text in ("Log", "Debug") and ignore_log_info is True:
            continue

        # For each result
        for l_val in l_results.getchildren():

            l_tag = l_val.tag

            # --------------------------------------------------------------------------
            # Common properties: subnet, host, threat, raw_description
            # --------------------------------------------------------------------------
            if l_tag in ("subnet", "host", "threat"):
                # All text vars can be processes both.
                try:
                    setattr(l_partial_result, l_tag, l_val.text)
                except (TypeError, ValueError) as e:
                    logging.warning(
                        "%s is not a valid value for %s property in %s vulnerability. skipping vulnerability..."
                        % (l_val.text,
                           l_tag,
                           l_partial_result.id))
                    logging.debug(e)
                    continue

            elif l_tag == "description":
                try:
                    setattr(l_partial_result, "raw_description", l_val.text)
                except TypeError as e:
                    logging.warning("%s is not a valid description for %s vulnerability. skipping vulnerability..."
                                    % (l_val.text,
                                       l_vid))
                    logging.debug(e)
                    continue

            # --------------------------------------------------------------------------
            # Port
            # --------------------------------------------------------------------------
            elif l_tag == "port":

                # Looking for port as format: https (443/tcp)
                l_port = port_regex_specific.search(l_val.text)
                if l_port:
                    l_service = l_port.group(1)
                    l_number = int(l_port.group(2))
                    l_proto = l_port.group(3)

                    try:
                        l_partial_result.port = OpenVASPort(l_service,
                                                            l_number,
                                                            l_proto)
                    except (TypeError, ValueError) as e:
                        logging.warning("%s is not a valid port for %s vulnerability. skipping vulnerability..."
                                        % (l_val.text,
                                           l_vid))
                        logging.debug(e)
                        continue
                else:
                    # Looking for port as format: general/tcp
                    l_port = port_regex_generic.search(l_val.text)
                    if l_port:
                        l_service = l_port.group(1)
                        l_proto = l_port.group(2)

                        try:
                            l_partial_result.port = OpenVASPort(l_service, 0, l_proto)
                        except (TypeError, ValueError) as e:
                            logging.warning("%s is not a valid port for %s vulnerability. skipping vulnerability..."
                                            % (l_val.text,
                                               l_vid))
                            logging.debug(e)
                            continue

            # --------------------------------------------------------------------------
            # NVT
            # --------------------------------------------------------------------------
            elif l_tag == "nvt":

                # The NVT Object
                l_nvt_object = OpenVASNVT()
                try:
                    l_nvt_object.oid = l_val.attrib['oid']
                except TypeError as e:
                    logging.warning("%s is not a valid NVT oid for %s vulnerability. skipping vulnerability..."
                                    % (l_val.attrib['oid'],
                                       l_vid))
                    logging.debug(e)
                    continue

                # Sub nodes of NVT tag
                l_nvt_symbols = [x for x in dir(l_nvt_object) if not x.startswith("_")]

                for l_nvt in l_val.getchildren():
                    l_nvt_tag = l_nvt.tag

                    # For each xml tag...
                    if l_nvt_tag in l_nvt_symbols:

                        # For tags with content, like: <cert>blah</cert>
                        if l_nvt.text:

                            # For filter tags like <cve>NOCVE</cve>
                            if l_nvt.text.startswith("NO"):
                                try:
                                    setattr(l_nvt_object, l_nvt_tag, "")
                                except (TypeError, ValueError) as e:
                                    logging.warning(
                                        "Empty value is not a valid NVT value for %s property in %s vulnerability. skipping vulnerability..."
                                        % (l_nvt_tag,
                                           l_vid))
                                    logging.debug(e)
                                    continue

                            # Tags with valid content
                            else:
                                # --------------------------------------------------------------------------
                                # Vulnerability IDs: CVE-..., BID..., BugTraq...
                                # --------------------------------------------------------------------------
                                if l_nvt_tag.lower() in vulnerability_IDs:
                                    l_nvt_text = getattr(l_nvt, "text", "")
                                    try:
                                        setattr(l_nvt_object, l_nvt_tag, l_nvt_text.split(","))
                                    except (TypeError, ValueError) as e:
                                        logging.warning(
                                            "%s value is not a valid NVT value for %s property in %s vulnerability. skipping vulnerability..."
                                            % (l_nvt_text,
                                               l_nvt_tag,
                                               l_vid))
                                        logging.debug(e)
                                    continue

                                else:
                                    l_nvt_text = getattr(l_nvt, "text", "")
                                    try:
                                        setattr(l_nvt_object, l_nvt_tag, l_nvt_text)
                                    except (TypeError, ValueError) as e:
                                        logging.warning(
                                            "%s value is not a valid NVT value for %s property in %s vulnerability. skipping vulnerability..."
                                            % (l_nvt_text,
                                               l_nvt_tag,
                                               l_vid))
                                        logging.debug(e)
                                    continue

                        # For filter tags without content, like: <cert/>
                        else:
                            try:
                                setattr(l_nvt_object, l_nvt_tag, "")
                            except (TypeError, ValueError) as e:
                                logging.warning(
                                    "Empty value is not a valid NVT value for %s property in %s vulnerability. skipping vulnerability..."
                                    % (l_nvt_tag,
                                       l_vid))
                                logging.debug(e)
                                continue

                # Get CVSS
                cvss_candidate = l_val.find("tags")
                if cvss_candidate is not None and getattr(cvss_candidate, "text", None):
                    # Extract data
                    cvss_tmp = cvss_regex.search(cvss_candidate.text)
                    if cvss_tmp:
                        l_nvt_object.cvss_base_vector = cvss_tmp.group(2) if len(cvss_tmp.groups()) >= 2 else ""

                # Add to the NVT Object
                try:
                    l_partial_result.nvt = l_nvt_object
                except (TypeError, ValueError) as e:
                    logging.warning(
                        "NVT oid %s is not a valid NVT value for %s vulnerability. skipping vulnerability..."
                        % (l_nvt_object.oid,
                           l_vid))
                    logging.debug(e)
                    continue

            # --------------------------------------------------------------------------
            # Unknown tags
            # --------------------------------------------------------------------------
            else:
                # Unrecognised tag
                logging.warning("%s tag unrecognised" % l_tag)

        # Add to the return values
        m_return_append(l_partial_result)

    return m_return

# ------------------------------------------------------------------------------
#
# High level exceptions
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
class VulnscanException(Exception):
    """Base class for OpenVAS exceptions."""


# ------------------------------------------------------------------------------
class VulnscanAuthFail(VulnscanException):
    """Authentication failure."""


# ------------------------------------------------------------------------------
class VulnscanServerError(VulnscanException):
    """Error message from the OpenVAS server."""


# ------------------------------------------------------------------------------
class VulnscanClientError(VulnscanException):
    """Error message from the OpenVAS client."""


# ------------------------------------------------------------------------------
class VulnscanProfileError(VulnscanException):
    """Profile error."""


# ------------------------------------------------------------------------------
class VulnscanTargetError(VulnscanException):
    """Target related errors."""


# ------------------------------------------------------------------------------
class VulnscanScanError(VulnscanException):
    """Task related errors."""


# ------------------------------------------------------------------------------
class VulnscanVersionError(VulnscanException):
    """Wrong version of OpenVAS server."""


# ------------------------------------------------------------------------------
class VulnscanTaskNotFinishedError(VulnscanException):
    """Wrong version of OpenVAS server."""


# ------------------------------------------------------------------------------
class VulnscanAuditNotRunningError(VulnscanException):
    """Wrong version of OpenVAS server."""


# ------------------------------------------------------------------------------
class VulnscanAuditNotFoundError(VulnscanException):
    """Wrong version of OpenVAS server."""


# ------------------------------------------------------------------------------
#
# High level interface
#
# ------------------------------------------------------------------------------
class AuditNotRunning(object):
    pass


class VulnscanManager7(object):
    """
    High level interface to the OpenVAS server.

    ..warning: Intended to only be compatible with OMP 7.0.
    """

    # ----------------------------------------------------------------------
    #
    # Methods to manage OpenVAS
    #
    # ----------------------------------------------------------------------
    def __init__(self, host, user, password, port=9390, timeout=None, ssl_verify=False):
        """
        :param host: The host where the OpenVAS server is running.
        :type host: str

        :param user: Username to connect with.
        :type user: str

        :param password: Password to connect with.
        :type password: str

        :param port: Port number of the OpenVAS server.
        :type port: int

        :param ssl_verify: Whether or not to verify SSL certificates from the server
        :type ssl_verify: bool

        :raises: VulnscanServerError, VulnscanAuthFail, VulnscanVersionError
        """

        if not isinstance(host, str):
            raise TypeError("Expected string, got %r instead" % type(host))
        if not isinstance(user, str):
            raise TypeError("Expected string, got %r instead" % type(user))
        if not isinstance(password, str):
            raise TypeError("Expected string, got %r instead" % type(password))
        if isinstance(port, int):
            if not (0 < port <= 65535):
                raise ValueError("Port number must be in range (0, 65535]")
        else:
            raise TypeError("Expected int, got %r instead" % type(port))

        m_time_out = None
        if timeout:
            if isinstance(timeout, int):
                if timeout < 1:
                    raise ValueError("Timeout value must be greater than 0.")
                else:
                    m_time_out = timeout
            else:
                raise TypeError("Expected int, got %r instead" % type(timeout))

        # Create the manager
        try:
            self._manager = get_connector(host, user, password, port, m_time_out, ssl_verify)
        except ServerError as e:
            raise VulnscanServerError("Error while connecting to the server: %s" % e.message)
        except AuthFailedError:
            raise VulnscanAuthFail("Error while trying to authenticate into the server.")
        except RemoteVersionError:
            raise VulnscanVersionError("Invalid OpenVAS version in remote server.")

        #
        # Flow control

        # Error counter
        self._error_counter = 0

        # Old progress
        self._old_progress = 0.0

        # Init various vars
        self._function_handle = None
        self._task_id = None
        self._target_id = None

    # ----------------------------------------------------------------------
    def launch_scan(self, target, **kwargs):
        """
        Launch a new audit in OpenVAS.

        This is an example code to launch an OpenVAS scan and wait for it
        to complete::

            from threading import Semaphore
            from functools import partial

            def my_print_status(i): print str(i)

            def my_launch_scanner():

                Sem = Semaphore(0)

                # Configure
                manager = VulnscanManager("localhost", "admin", "admin)

                # Launch
                manager.launch_scan(
                    target,
                    profile = "empty",
                    callback_end = partial(lambda x: x.release(), sem),
                    callback_progress = my_print_status
                )

                # Wait
                Sem.acquire()

                # Finished scan
                print "finished!"

            # >>> my_launch_scanner() # It can take some time
            # 0
            # 10
            # 39
            # 60
            # 90
            # finished!

        :param target: Target to audit.
        :type target: str

        :param schedule: Schedule ID to use for the scan. (create_schedule provides this)
        :type schedule: str

        :param profile: Scan profile in the OpenVAS server.
        :type profile: str

        :param callback_end: If this param is set, the process will run in background
                             and call the function specified in this var when the
                             scan ends.
        :type callback_end: function

        :param callback_progress: If this param is set, it will be called every 10 seconds,
                                  with the progress percentaje as a float.
        :type callback_progress: function(float)

        :return: ID of the audit and ID of the target: (ID_scan, ID_target)
        :rtype: (str, str)
        """

        profile = kwargs.get("profile", "Full and fast")
        schedule = kwargs.get("schedule",None)
        call_back_end = kwargs.get("callback_end", None)
        call_back_progress = kwargs.get("callback_progress", None)
        if not (isinstance(target, str) or isinstance(target, Iterable)):
            raise TypeError("Expected str or iterable, got %r instead" % type(target))
        if not isinstance(profile, str):
            raise TypeError("Expected string, got %r instead" % type(profile))

        # Generate the random names used
        m_target_name = "openvas_lib_target_%s_%s" % (target, generate_random_string(20))
        m_job_name = "openvas_lib_scan_%s_%s" % (target, generate_random_string(20))

        # Create the target
        try:
            m_target_id = self._manager.create_target(m_target_name, target,
                                                       "Temporal target from OpenVAS Lib", "")
        except ServerError as e:
            raise VulnscanTargetError("The target already exits on the server. Error: %s" % e.message)

        # Get the profile ID by their name
        try:
            tmp = self._manager.get_configs_ids(profile)
            m_profile_id = tmp[profile]
        except ServerError as e:
            raise VulnscanProfileError("The profile select not exits int the server. Error: %s" % e.message)
        except KeyError:
            raise VulnscanProfileError("The profile select not exits int the server")

        # Create task
        try:
            m_task_id = self._manager.create_task(m_job_name, m_target_id, config=m_profile_id,
                                                   schedule=schedule, comment="scan from OpenVAS lib")
        except ServerError as e:
            raise VulnscanScanError("The target selected doesnn't exist in the server. Error: %s" % e.message)

        # Start the scan
        try:
            self._manager.start_task(m_task_id)
        except ServerError as e:
            raise VulnscanScanError(
                "Unknown error while try to start the task '%s'. Error: %s" % (m_task_id, e.message))

        # Callback is set?
        if call_back_end or call_back_progress:
            # schedule a function to run each 10 seconds to check the estate in the server
            self._task_id = m_task_id
            self._target_id = m_target_id
            self._function_handle = self._callback(call_back_end, call_back_progress)

        return m_task_id, m_target_id

    # ----------------------------------------------------------------------
    @property
    def task_id(self):
        """
        :returns: OpenVAS task ID.
        :rtype: str
        """
        return self._task_id

    # ----------------------------------------------------------------------
    @property
    def target_id(self):
        """
        :returns: OpenVAS target ID.
        :rtype: str
        """
        return self._target_id

    # ----------------------------------------------------------------------
    def create_port_list(self, name, port_range, comment=""):
        """
        Creates a port list in OpenVAS.

        :param name: name to the port list
        :type name: str

        :param port_range:Port ranges. Should be a string of the form "T:22-80,U:53,88,1337"
        :type hosts: str

        :param comment: comment to be attached to the port range
        :type hosts: str

        :return: the ID of the created port range.
        :rtype: str

        :raises: ClientError, ServerError TODO
        """
        try:
            m_port_list_id = self._manager.create_port_list(name, port_range, "")
        except ServerError as e:
            raise ServerError("Error while attempting to create port_list: %s" % e.message)
        return m_port_list_id

    # ----------------------------------------------------------------------
    def create_schedule(self, name, hour, minute, month, day, year, period=None, duration=None, timezone="UTC"):
        """
        Creates a schedule in the OpenVAS server.

        :param name: name to the schedule
        :type name: str

        :param hour: hour at which to start the schedule, 0 to 23
        :type hour: str

        :param minute: minute at which to start the schedule, 0 to 59
        :type minute: str

        :param month: month at which to start the schedule, 1-12
        :type month: str

        :param year: year at which to start the schedule
        :type year: str

        :param timezone: The timezone the schedule will follow. The format of a timezone is the same as that of the TZ environment variable on GNU/Linux systems
        :type timezone: str

        :param period:How often the Manager will repeat the scheduled task. Assumed unit of days
        :type period: str

        :param duration: How long the Manager will run the scheduled task for. Assumed unit of hours
        :type period: str

        :return: the ID of the created schedule.
        :rtype: str

        :raises: ClientError, ServerError
        """
        try:
            m_schedule_id = self._manager.create_schedule(name, hour, minute, month, day, year, period, duration, timezone)
        except ServerError as e:
            raise ServerError("Error while attempting to create schedule: %s" % e.message)
        return m_schedule_id

    # ----------------------------------------------------------------------
    def create_target(self, name, hosts, comment="", port_list="Default"):
        """
        Creates a target in OpenVAS.

        :param name: name to the target
        :type name: str

        :param hosts: target list. Can be only one target or a list of targets
        :type hosts: str | list(str)

        :return: the ID of the created target.
        :rtype: str

        :raises: ClientError, ServerError TODO
        """
        try:
            m_target_id = self._manager.create_target(name, hosts, "", port_list)
        except ServerError as e:
            raise VulnscanTargetError("Error while attempting to create target: %s" % e.message)
        return m_target_id

    # ----------------------------------------------------------------------
    def delete_scan(self, task_id):
        """
        Delete specified scan ID in the OpenVAS server.

        :param task_id: Scan ID.
        :type task_id: str

        :raises: VulnscanAuditNotFoundError
        """
        try:
            self._manager.delete_task(task_id)
        except AuditNotRunningError as e:
            raise VulnscanAuditNotFoundError(e)

    # ----------------------------------------------------------------------
    def delete_target(self, target_id):
        """
        Delete specified target ID in the OpenVAS server.

        :param target_id: Target ID.
        :type target_id: str
        """
        self._manager.delete_target(target_id)

    # ----------------------------------------------------------------------
    def get_results(self, task_id):
        """
        Get the results associated to the scan ID.

        :param task_id: Scan ID.
        :type task_id: str

        :return: Scan results.
        :rtype: list(OpenVASResult)

        :raises: ServerError, TypeError
        """

        if not isinstance(task_id, str):
            raise TypeError("Expected string, got %r instead" % type(task_id))

        try:
            m_response = self._manager.get_results(task_id)
        except ServerError as e:
            raise VulnscanServerError("Can't get the results for the task %s. Error: %s" % (task_id, e.message))

        return m_response

    # ----------------------------------------------------------------------
    def get_raw_xml(self, task_id):
        """
        Get the results associated to the scan ID.

        :param task_id: Scan ID.
        :type task_id: str

        :return: Scan results. in XML ElementTree form
        :rtype: ElementTree Element

        :raises: ServerError, TypeError
        """

        if not isinstance(task_id, str):
            raise TypeError("Expected string, got %r instead" % type(task_id))

        if self._manager.is_task_running(task_id):
            raise VulnscanTaskNotFinishedError(
                "Task is currently running. Until it not finished, you can't obtain the results.")

        try:
            m_response = self._manager.get_results(task_id)
        except ServerError as e:
            raise VulnscanServerError("Can't get the results for the task %s. Error: %s" % (task_id, e.message))

        return m_response

    # ----------------------------------------------------------------------
    def get_report_id(self, scan_id):

        if not isinstance(scan_id, str):
            raise TypeError("Expected string, got %r instead" % type(scan_id))

        return self._manager.get_report_id(scan_id)

    # ----------------------------------------------------------------------
    def get_report_html(self, report_id):

        if not isinstance(report_id, str):
            raise TypeError("Expected string, got %r instead" % type(report_id))

        return self._manager.get_report_html(report_id)
        # ----------------------------------------------------------------------

    # ----------------------------------------------------------------------
    def get_report_xml(self, report_id):

        if not isinstance(report_id, str):
            raise TypeError("Expected string, got %r instead" % type(report_id))

        return self._manager.get_report_xml(report_id)
        # ----------------------------------------------------------------------

    # ----------------------------------------------------------------------
    def get_report_pdf(self, report_id):

        if not isinstance(report_id, str):
            raise TypeError("Expected string, got %r instead" % type(report_id))

        return self._manager.get_report_pdf(report_id)

    # ----------------------------------------------------------------------
    def get_progress(self, task_id):
        """
        Get the progress of a scan.

        :param task_id: Scan ID.
        :type task_id: str

        :return: Progress percentage (between 0.0 and 100.0).
        :rtype: float
        """
        if not isinstance(task_id, str):
            raise TypeError("Expected string, got %r instead" % type(task_id))

        return self._manager.get_tasks_progress(task_id)

    # ----------------------------------------------------------------------
    def stop_audit(self, task_id):
        """
        Stops specified scan ID in the OpenVAS server.

        :param task_id: Scan ID.
        :type task_id: str

        :raises: VulnscanAuditNotFoundError
        """
        try:
            self._manager.stop_task(task_id)
        except AuditNotRunningError as e:
            raise VulnscanAuditNotFoundError(e)
    # ----------------------------------------------------------------------
    def get_scan_status(self, task_id):
        """
        Gets the status of the specified scan ID in the OpenVAS server.

        :param task_id: Scan ID.
        :type task_id: str

        :raises: VulnscanAuditNotFoundError
        """
        statusXML = None
        try:
            statusXML = self._manager.get_task_status(task_id)
        except ServerError as e:
            raise e
        if statusXML:
            return statusXML
        return None

    # ----------------------------------------------------------------------
    @property
    def get_profiles(self):
        """
        :return: All available profiles.
        :rtype: {profile_name: ID}
        """
        return self._manager.get_configs_ids()

    # ----------------------------------------------------------------------
    @property
    def get_all_scans(self):
        """
        :return: All scans.
        :rtype: {scan_name: ID}
        """
        return self._manager.get_tasks_ids()

    # ----------------------------------------------------------------------
    @property
    def get_running_scans(self):
        """
        :return: All running scans.
        :rtype: {scan_name: ID}
        """
        return self._manager.get_tasks_ids_by_status("Running")

    # ----------------------------------------------------------------------
    @property
    def get_finished_scans(self):
        """
        :return: All finished scans.
        :rtype: {scan_name: ID}
        """
        return self._manager.get_tasks_ids_by_status("Done")

    # ----------------------------------------------------------------------
    @set_interval(10.0)
    def _callback(self, func_end, func_status):
        """
        This callback function is called periodically from a timer.

        :param func_end: Function called when task end.
        :type func_end: funtion pointer

        :param func_status: Function called for update task status.
        :type func_status: funtion pointer
        """
        # Check if audit was finished
        try:
            if not self._manager.is_task_running(self.task_id):
                # Task is finished. Stop the callback interval
                self._function_handle.set()

                # Call the callback function
                if func_end:
                    func_end()

                # Reset error counter
                self._error_counter = 0

        except (ClientError, ServerError, Exception) as e:
            self._error_counter += 1

            # Checks for error number
            if self._error_counter >= 5:
                # Stop the callback interval
                self._function_handle.set()

                func_end()

        if func_status:
            try:
                t = self.get_progress(self.task_id)

                # Save old progress
                self._old_progress = t

                func_status(1.0 if t == 0.0 else t)

            except (ClientError, ServerError, Exception) as e:

                func_status(self._old_progress)

    def parse_results(self, results, parser=results_parser):
        """
        Parse results with the specified parser

        :param results: Scan results
        :type results: ElementTree Element

        :param parser: Function called for update task status.
        :type parser: function
        """
        return parser(results)

    def resume_audit(self, task_id):
        """
        Resume stopped task by specified scan ID in the OpenVAS server.

        :param task_id: Scan ID.
        :type task_id: str

        :raises: VulnscanAuditNotFoundError
        """
        try:
            self._manager.resume_task(task_id)
        except ClientError as e:
            raise VulnscanServerError("Cannot resume the task %s. Error: %s" % (task_id, e.message))
    # ----------------------------------------------------------------------
