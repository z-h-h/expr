import re
import os
import time
import getpass
import socket


class BugReport:
    def __init__(self):
        self.bug_type = ""
        self.bug_category = ""
        self.bug_file = ""
        self.bug_line = 0
        self.path_length = 1
        self.report_file = ''
        self.exceptional = False


class UserInfo:
    def __init__(self):
        self.realdir = ''
        self.username = ''
        self.hostname = ''
        self.curr_dir = ''
        self.date = ''
        self.html_title = 'Canalyze++ Analysis Results'
        self.author = ''


def scanFile(filename):
    bug = BugReport()
    try:
        f = open(filename)
        while True:
            line = f.readline()

            m = re.match('<!-- BUGTYPE (.*) -->', line)
            if m:
                bug.bug_type = m.group(1)
                continue

            m = re.match('<!-- BUGCATEGORY (.*) -->', line)
            if m:
                bug.bug_category = m.group(1)
                continue

            m = re.match('<!-- BUGFILE (.*) -->', line)
            if m:
                bug.bug_file = os.path.basename(m.group(1))
                continue

            m = re.match('<!-- BUGLINE (.*) -->', line)
            if m:
                bug.bug_line = int(m.group(1))
                continue

            m = re.match('<!-- BUGPATHLENGTH (.*) -->', line)
            if m:
                bug.path_length = int(m.group(1))
                continue

            if re.match('<!-- EXCEPTIONAL -->', line):
                bug.exceptional = True
                continue

            if re.match('<!-- BUGMETAEND -->', line):
                break
    finally:
        f.close()
    bug.report_file = os.path.basename(filename)
    return bug


def generateIndex(report_dir, f, runpath):
    # Init user info
    userinfo = UserInfo()
    userinfo.realdir =  \
        os.path.dirname(os.path.realpath(os.path.abspath(runpath)))
    userinfo.username = getpass.getuser()
    userinfo.hostname = socket.gethostname()
    userinfo.curr_dir = os.getcwd()
    userinfo.date = time.strftime('%Y-%m-%d %H:%M')

    addHtmlHeaderJavascriptCSS(f, userinfo.html_title)
    addUserInfo(f, userinfo)
    reportlist = os.listdir(report_dir)
    filefilter = re.compile('report-.*[.]html$')
    buglist = []
    bugStat = {}
    for report in reportlist:
        if filefilter.match(report):
            bug = scanFile(report_dir + os.sep + report)
            bugStat[bug.bug_type] = bugStat.get(bug.bug_type, 0) + 1
            buglist.append(bug)

    addSummaryTable(f, bugStat)
    addReportTable(f, buglist)
    copyFiles(userinfo.realdir, report_dir)


def addHtmlHeaderJavascriptCSS(f, html_title):
    f.write('''
<html>
<head>
<title>''' + html_title + '''</title>
''')

    f.write(r'''
<link type="text/css" rel="stylesheet" href="scanview.css"/>
<script src="sorttable.js"></script>
<script language='javascript' type="text/javascript">
function SetDisplay(RowClass, DisplayVal)
{
  var Rows = document.getElementsByTagName("tr");
  for ( var i = 0 ; i < Rows.length; ++i ) {
    if (Rows[i].className == RowClass) {
      Rows[i].style.display = DisplayVal;
    }
  }
}

function CopyCheckedStateToCheckButtons(SummaryCheckButton) {
  var Inputs = document.getElementsByTagName("input");
  for ( var i = 0 ; i < Inputs.length; ++i ) {
    if (Inputs[i].type == "checkbox") {
      if(Inputs[i] != SummaryCheckButton) {
        Inputs[i].checked = SummaryCheckButton.checked;
        Inputs[i].onclick();
          }
    }
  }
}

function returnObjById( id ) {
    if (document.getElementById)
        var returnVar = document.getElementById(id);
    else if (document.all)
        var returnVar = document.all[id];
    else if (document.layers)
        var returnVar = document.layers[id];
    return returnVar;
}

var NumUnchecked = 0;

function ToggleDisplay(CheckButton, ClassName) {
  if (CheckButton.checked) {
    SetDisplay(ClassName, "");
    if (--NumUnchecked == 0) {
      returnObjById("AllBugsCheck").checked = true;
    }
  }
  else {
    SetDisplay(ClassName, "none");
    NumUnchecked++;
    returnObjById("AllBugsCheck").checked = false;
  }
}
</script>
<!-- SUMMARYENDHEAD -->
</head>
<body>
''')


def addUserInfo(f, userinfo):
    f.write('''
<h1>%s</h1>
<h3>See Author %s</h3>
<table>
<tr><th>User:</th><td>%s@%s</td></tr>
<tr><th>Working Directory:</th><td>%s</td></tr>
<tr><th>Date:</th><td>%s</td></tr>
</table>''' %
            (userinfo.html_title, userinfo.author, userinfo.username,
             userinfo.hostname, userinfo.curr_dir,
             userinfo.date))


def addSummaryTable(f, bugStat):
    f.write('<h2>Bug Summary</h2>')
    # add table header
    f.write('''
<table>
<thead><tr>
<td>Bug Type</td><td>Quantity</td>
<td class="sorttable_nosort">Display?</td>
</tr></thead>
<tr style="font-weight:bold">
<td class="SUMM_DESC">All Bugs</td>
<td class="Q">$TotalBugs</td>
<td><center><input type="checkbox" id="AllBugsCheck"
onClick="CopyCheckedStateToCheckButtons(this);" checked/></center></td>
</tr>''')

    # add table content--bug summary
    for key in bugStat.keys():
        f.write('''
<tr>
<td class="SUMM_DESC">%s</td><td class="Q">%d</td>
<td><center>
<input type="checkbox"
onClick="ToggleDisplay(this,'bt_%s');" checked/>
</center></td>
</tr>''' % (key, bugStat[key], key.lower().replace(' ', '_')))

    f.write('</table>')


def addReportTable(f, buglist):
    f.write('''
<h2>Reports</h2>

<table class="sortable" style="table-layout:automatic">
<thead><tr>
  <td>No.</td>
  <td>Bug Group</td>
  <td class="sorttable_sorted">Bug Type<span id="sorttable_sortfwdind">&nbsp;&#x25BE;</span></td>
  <td>File</td>
  <td class="Q">Line</td>
  <td class="Q">Path Length</td>
  <td class="sorttable_nosort"></td>
  <!-- REPORTBUGCOL -->
</tr></thead>
<tbody>''')

    # add buglist in report table
    import operator
    buglist.sort(key=operator.attrgetter('bug_type'))
    i = 1
    for bug in buglist:
        id = 'id="exceptional"' if bug.exceptional else ''
        f.write('''
<tr %s class="bt_%s"><td class="Q">%d</td><td class="DESC">%s</td><td class="DESC">%s</td><td>%s</td><td class="Q">%d</td><td class="Q">%d</td><td><a href="%s#EndPath">View Report</a></td>
</tr>''' % (id, bug.bug_type.lower().replace(' ', '_'), i, bug.bug_category,
            bug.bug_type, bug.bug_file, bug.bug_line, bug.path_length,
            bug.report_file))
        i += 1

    f.write('''
</tr></tbody></table>
</body></html>''')


def copyFiles(realdir, report_dir):
    import shutil
    filenames = ('scanview.css', 'sorttable.js')
    shutil.copyfile(realdir + os.sep + filenames[0],
                    report_dir + os.sep + filenames[0])
    shutil.copyfile(realdir + os.sep + filenames[1],
                    report_dir + os.sep + filenames[1])


def generate(reports):
    with open(reports + os.sep + 'index.html', 'w') as index:
        generateIndex(reports, index, __file__)
