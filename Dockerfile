FROM williamwxl/chromium-xvfb-py3.6

COPY requirements.txt ./

RUN mkdir /root/.pip && \
    wget -O /root/.pip/pip.conf http://ojiqea97q.bkt.clouddn.com/mirrors/pip.conf && \
    ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo Asia/Shanghai > /etc/timezone && \
    pip install --no-cache-dir -r requirements.txt

ENV app=fetch
COPY . /usr/local/lib/python3.6/site-packages
COPY . .

CMD "python" "cmd/${app}.py"