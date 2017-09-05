
# sysenv

**This utility is NOT done yet!**

NOTE: This utility works with `bash` only!


    
## Installation

#### 1. `git clone` to your local disk.

Suppose it's cloned to `/sysenv`.
The cloned directory should be readable by everyone.

#### 2. Integrate `sysenv` into bash.

Just run
```
sudo python /sysenv/install.py
```

A line of `source /sysenv/env.bashrc` will be added to the proper file.
- For Ubuntu: Added to the top of `/etc/bash.bashrc`
- For CentOS: Added to the top of `/etc/bashrc`
- For other OS: The installer can't do it for you. Manually add the above line into your system-wide bash profile.


*NOTE:*
- *`/sysenv/env.bashrc` is sourced no matter bash is interactive or not.*
- *`/sysenv/env.bashrc` is sourced even if `bash` is started by SSH.*
- *Idempotence: to source `/sysenv/env.bashrc` many times is OK.*


## Usage

#### 1. Use `~/env.conf` to define environment variables.

#### 2. Use `env-xxx` functions in `bash`.



## Warning

NOT every corner cases are tested. So please don't include any **strange** characters in path string.

For example:
- Back slashes `\`
- Commas `:`
- Asterisks `*`
- Dollars (reserved for enviroment variables) `$`


Whitespaces ` `, single quotes `'` and double quotes `"` should work.

However, it's still strongly suggested **NOT** including these characters in path string,
since not every program and library handles them very well.
