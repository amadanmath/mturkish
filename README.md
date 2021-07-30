## MTurkish

# Rationale

You can do everything already using AWS CLI. Why another library?
The way I write HITs is somewhat opinionated, because I needed to handle
multimedia and structured data, and also large quantities of data.  This
little tool simplifies the process, by assuming certain constants about the
way I use AMT and the way I write HITs.

# Installation

    python -m pip install git+https://github.com/amadanmath/mturkish
    
# Usage

* Prepare sample data in JSONL format.
* Use the sample MTurk HIT HTML template and create a HIT type and layout using
the website.
* Get the HIT type and layout ID:

    ![How to get HIT type and layout
ID](https://docs.aws.amazon.com/AWSMechTurk/latest/AWSMturkAPI/images/AWS-Mturk-Existing-Projects-LayoutId-01.jpg)

* Create HITs with JSONL data:

    ```bash
    mturkish -s -p kirt make-hits -i $HITTypeId $LayoutId < data.jsonl > hit_ids.lst
    ```
        
* Use `-s` to use the sandbox, otherwise the real site will be used.
    Use `-p profile_name` if your profile is not `default` in
    `$HOME/.aws/credentials`. Both need to be used before the command
    (i.e. before `make-hits` in the previous example)

* You can make these parameters stick by using environment variables:

    ```bash
    export MTURKISH_SANDBOX=true
    export MTURKISH_PROFILE=kirt
    ```

    Then you can just write
    
    ```bash
    mturkish make-hits ...
    ```
    
* All `mturkish` commands return a JSON value, unless `--ids/-i` option is
  used. I recommend the excellent
  [`fx` tool](https://github.com/antonmedv/fx)
  for viewing and processing JSON, whether saved or piped in.

* You can use `list-assignments` to check your HIT assignments, and retrieve
  results (which will be under `[].Answer`). For example,

    ```bash
    mturkish list-assignments $(< hit_ids.lst) > assignments.json
    fx assignments.json
    ```
    
* You can approve or reject individual assignments by their assignment ID, or all assignments (`-a`) for
  given HIT IDs:
  
    ```bash
    mturkish approve -m 'Good work!' $AssignmentId...
    mturkish reject -a -m 'Do better!' $HITId...
    ```
  
* You can expire HITs:

    ```bash
    mturkish expire $HITId...
    ```
    
* And delete them (but only if they are reviewable, and all assignments are
  approved or rejected):
  
    ```bash
    mturkish delete $HITId...
    ```
  
