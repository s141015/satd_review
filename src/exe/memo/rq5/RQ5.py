# coding: UTF-8

import os
import commands
import sys
import re #正規表現用
import json
import codecs
import numpy
from time import sleep
import subprocess
import multiprocessing
import math
import urlparse
import csv #引っかかる場合はpip installを

csv.field_size_limit(1000000000)
#python2
#使い方：「python review_extract.py openstack nova」 という具合．ignoreは使いまわしてもいいが０のがいい
#
#目的：レビューを通じて追加された/レビューですり抜けたSATDがその後どのくらいの期間残るかを調べる
#対象：current_revisonが明らかになってるSATD
#手順:
#0.「./data/result_RQ4_comments_(sub).csv」を２行目から呼び出す
#その後それぞれの行について，
#1.コメントのnumber->query.jsonからcurrent_revisionをとる．ないなら飛ばす
#2.git checkout
#3.ExtractComment.pyでそのリビジョンからコメントを取り，該当するコメントを探す．
#4.その行に対してstep1.plを起動する（改造の必要あり）
#5.結果をリザルトファイルに出力する

#対応するプロジェクトをDSフォルダでgit cloneしてくる必要あり．

#TODO:
#「./data/result_add_unreview_(sub).csv」についても同じ処理を行いたい


#============================================================================
# SATDgetより引用
#============================================================================

def file_search(): #このままでは使えない
    #find ../DS/{project}って感じになりそう．
    #string = subprocess.call("pwd")
    #print string
    #コマンドが動作しない．何がおかしいんだろう？
    #script = r"find ./DS/stripe-java -name \"*.java\" -print" #エスケープなしでいける？
    #string = subprocess.call(script)
    #check_output = 返り値が標準出力になる．(他のコマンドだと０が返ってくるのでこれが必要）
    if rev_count == 1 or rev_count == list_length: #初めと最後は全部見つける必要あり．
        string = subprocess.check_output("find ./DS/" + proj_name + " -name *." + lang + " -print",  shell=True)
    else:
        string = subprocess.check_output("git diff --name-only " + before_hash + " " + h +  " --diff-filter=ACMR *." + lang,  shell=True, cwd= './DS/' + proj_name )
    #diff-filter..A=追加，C=コピー，M=変更，R=リネーム．のあったフォルダ．Dは削除．
    #でもD以外（小文字のdとするのが良さそう)
    #先に１つ前のリビジョン，後に今のリビジョンとすること．逆だと追加，除去の判定が逆転して死ぬ．
    #print string  #for test
    return string

def checkout(hash): #RQ5用にproj_name -> sub_nameに変更してます
    try:
        string = subprocess.check_output("git checkout -f " + hash,  shell=True, cwd= './DS/' + sub_name)
    except subprocess.CalledProcessError as e:
        print e.output
        return 1
        
    print "str = " + string
    if string.find('reference is not a tree') >= 0: #fatal: reference is not a tree:って出力が来た場合
        return 1
    else:
        return 0

def comment_get(url, hash):
    is_diff = False #i行目がdiff箇所に該当するか否かを入力する．
    list = []
    comments = ""
    temp_str = "" #一時保存用文字列
    multi_line = False
    after_solo = False #１行コメント(//系)の直後ならTrueにする．単行コメントが連続するなら文字列をつなぐ．
    javadoc = False #javadocの文法である疑いがあるならtrue.その場合@もあればyieldを行わない．
    now_line = 1
    start_line = 0
    intro_id = ""
    now_filename = url #チェックアウトに合わせて変えていくファイル名 .DS/proj_nameまでを消したもの
    #print "pass:" + url
    now_filename = now_filename.replace('./DS/' + proj_name + '/', '', 1)
    #print "now_filename:" + now_filename
    #ファイル開閉処理が入ってないやん．
    try:
        with open(url, "r+") as f:
            line = f.readline()
            while line: #ここhttps://除外をやっておく？
                if (re.search(re.escape(r"http://"), line) or re.search(re.escape(r"https://"), line)) and multi_line == False: #http exclude
                    if after_solo == True: #単行コメントの直後の場合の処理
                        yield {"proj_name":proj_name, "pass":url, "comment":comments, "start_line":start_line, "end_line":now_line - 1, "SHA":hash, "now_filename":now_filename, "last_SHA":hash}
                    after_solo = False
                    now_line += 1 #continue前に次の行への処理は必須
                    line = f.readline()
                    continue
                elif re.search(re.escape(r"/*"), line) and multi_line == True: # /*
                    if after_solo == True: #単行コメントの直後の場合の処理
                        yield {"proj_name":proj_name, "pass":url, "comment":comments, "start_line":start_line, "end_line":now_line - 1, "SHA":hash, "now_filename":now_filename, "last_SHA":hash}
                    after_solo = False
                    multi_line = True
                    comments = line[line.find("/*"):-1] + "\n"
                    if re.match(re.escape(r"/*"), comments):
                        javadoc = True
                    start_line = now_line
                elif re.search(re.escape(r"*/"), line) and multi_line == True : # */ bool=trueの条件も追加
                    comments += line[0:line.index("*/")]
                    multi_line = False
                    #list.append([comments, start_line, now_line])
                    #blameするならこのタイミングがいいか？
                    #intro_id = blame(url, start_line)
                    after_solo = False
                    if javadoc == False or re.search(re.escape(r"TODO"), comments) or re.search(re.escape(r"XXX"), comments) or re.search(re.escape(r"FIXME"), comments): #javadocでない，もしくはTODO,FIXME,XXXのいずれかの語を含むなら
                        yield {"proj_name":proj_name, "pass":url, "comment":comments, "start_line":start_line, "end_line":now_line, "SHA":hash, "now_filename":now_filename, "last_SHA":hash} #dictはキーの順番保持しない．
                    javadoc == False
                elif re.search(re.escape(r"//"), line) and multi_line == False : #//
                    temp_str = line[line.find("//"):-1] #改行文字は除外しない index -> find
                    #list.append([comments, now_line, now_line]) #要素追加
                    #intro_id = blame(url, now_line)
                    if after_solo == True:
                        comments += temp_str
                    else:
                        comments = temp_str
                        start_line = now_line
                        after_solo = True
                elif re.search(re.escape(r"/*"), line) and re.search(re.escape(r"*/"), line) and multi_line == False : # /* 〜〜〜 */
                    comments = line[line.find("/*"):line.index("*/")+1]
                    #list.append([comments, now_line, now_line]) #要素追加
                    #intro_id = blame(url, now_line)
                    yield {"proj_name":proj_name, "pass":url, "comment":comments, "start_line":now_line, "end_line":now_line, "SHA":hash, "now_filename":now_filename, "last_SHA":hash}
                elif multi_line :
                    comments += line
                    if not re.search(re.escape(r"*"), line):
                        javadoc = False #javadocは行ごとに*が入ってる．
                else:
                    if after_solo == True: #単行コメントの直後の場合の処理
                        yield {"proj_name":proj_name, "pass":url, "comment":comments, "start_line":start_line, "end_line":now_line - 1, "SHA":hash, "now_filename":now_filename, "last_SHA":hash}
                        after_solo = False
                    else:
                        after_solo = False
                now_line += 1
                line = f.readline()
    except IOError:
        print "IOError occured"
#list2 = [list[0] for x in liar]

#return list #返り値はコメント，開始行，終了行の３要素を持ったリストのリスト


#python系のコメント規則を持つもの(#,'''でコメントをつけられるもの)についてはこっちで対処する．
#def comment_get2(url, hash):
def comment_get2(script, diff_data):
    print "script_len+1 = " + str(len(script)) + ", diff_data_len = " + str(len(diff_data))
    after_diff = False
    is_diff = False #i行目がdiff箇所に該当するか否かを入力する．
    list = []
    comments = "" #複数行まとめた文字列
    temp_str = "" #一時保存用文字列
    result = []
    multi_line = False
    after_solo = False #１行コメント(//系)の直後ならTrueにする．単行コメントが連続するなら文字列をつなぐ．
    javadoc = False #javadocの文法である疑いがあるならtrue.その場合@もあればyieldを行わない．
    now_line = 1
    start_line = 0
    intro_id = ""
    #now_filename = url #チェックアウトに合わせて変えていくファイル名 .DS/proj_nameまでを消したもの
    #print "pass:" + url
    #now_filename = now_filename.replace('./DS/' + proj_name + '/', '', 1)
    #print "now_filename:" + now_filename
    #ファイル開閉処理が入ってないやん．
    try:
        for line in script:
            #line = f.readline() #入力がリスト形式なのでここ変更すべき
            #while line: #ここhttps://除外をやっておく？
                after_diff = is_diff
                is_diff = diff_data[now_line] #todo:out of rangeになる
                #http://関連の対策はpythonでは不要
                if re.search(re.escape(r"'''"), line) and multi_line == False: # /*
                    if after_solo == True and after_diff == True: #単行コメントの直後の場合の処理
                        result.append(comments)
                    after_solo = False
                    multi_line = True
                    comments = line[line.find("'''"):-1] + "\n"
                    if re.match(re.escape(r"'''"), comments):
                        javadoc = True
                    start_line = now_line
                elif re.search(re.escape(r"'''"), line) and multi_line == True : # */ bool=trueの条件も追加
                    comments += line[0:line.index("'''")]
                    multi_line = False
                    #list.append([comments, start_line, now_line])
                    #blameするならこのタイミングがいいか？
                    #intro_id = blame(url, start_line)
                    after_solo = False
                    #if javadoc == False or re.search(re.escape(r"TODO"), comments) or re.search(re.escape(r"XXX"), comments) or re.search(re.escape(r"FIXME"), comments):
                    if 1: #javadocの心配はないので
                        #javadocでない，もしくはTODO,FIXME,XXXのいずれかの語を含むなら
                        result.append(comments)
                    javadoc == False
                elif re.search(re.escape(r"#"), line) and multi_line == False and is_diff == True: #//
                    temp_str = line[line.find("#"):-1] #改行文字は除外しない index -> find
                    #list.append([comments, now_line, now_line]) #要素追加
                    #intro_id = blame(url, now_line)
                    if after_solo == True and is_diff == True:
                        comments += temp_str
                    else:
                        comments = temp_str
                        start_line = now_line
                        after_solo = True
                elif re.search(re.escape(r"'''"), line) and re.search(re.escape(r"'''"), line) and multi_line == False : # /* 〜〜〜 */
                    comments = line[line.find("'''"):line.index("'''")+1]
                    #list.append([comments, now_line, now_line]) #要素追加
                    #intro_id = blame(url, now_line)
                    result.append(comments)
                elif multi_line and is_diff == True:
                    comments += line
                    if not re.search(re.escape(r"*"), line):
                        javadoc = False #javadocは行ごとに*が入ってる．
                else:
                    if after_solo == True: #単行コメントの直後の場合の処理
                        result.append(comments)
                        after_solo = False
                    else:
                        after_solo = False
                now_line += 1
                #line = f.readline()
    except IOError:
        print "IOError occured"
    return result
#list2 = [list[0] for x in liar]

#return list #返り値はコメント，開始行，終了行の３要素を持ったリストのリスト



def detect(commentList):
    SATDComments = 0
    result = []
    temp_list = [] #value個ずつ読むときに使う．
    string = "" #detectorへの入力文字列
    id = 0
    id2 = 0
    value = 300 #１度に同時にでDetectorに処理してもらうコメント数．適宜増減させよう．
    p = os.getcwd() #SATDgetのディレクトリが出てきます
    print p
    det = p + "/srca/satd_detector.jar" #detectorのフルパス
    
    print commentList
    comlistlen = len(commentList) # commentListの長さ
    print "Detecting SATD..."
    for comment in commentList:
        
        #ここへ＊の消去処理を加えるべきか？
        n_delete = comment #\n_delete.つまり改行消した版の文字列をここへ突っ込む．
        n_delete = n_delete.replace('\r\n', ' ') #\rのreplaceも入れるべきか？
        n_delete = n_delete.replace('\n', ' ') #\rのreplaceも入れるべきか？
        n_delete = n_delete.replace('\\n', ' ')
        commentList[id] = n_delete
        
        #ここから大改造．
        temp_list.append(comment)
        #string += n_delete + "\n"
        string += n_delete.encode("utf-8") + "\n" #エラー対策
        
        if (id + 1) % value == 0 or comlistlen - id == 1: #100回読んだor commentListが最後なら実行
            satd_detector = subprocess.Popen("java -jar " + det + " test", stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) # 最後の「,encoding='utf-8'」」はエラーが出たので省略．
            
            #string = string.encode("utf-8") #190620:一時停止中
            (stdout, stderr) = satd_detector.communicate(string) #ここが入力箇所．処理が遅い（約３秒）
            #print n_delete
            #Open a process with the SATD Detector tool to test the current comment text
            #print "STDOUT:" + stdout #必要に応じて使用する．
            strlist = [] #detectorの出力を行単位で入れる変数
            strlist = stdout.splitlines()
            list_len = len(temp_list) #要素が１００ない場合に使う．
            print "strlist:" + str(len(temp_list)) + " out_line:" + str(len(strlist)) + " id:" + str(id)
            #print "comment::" + n_delete
            #comment.commentTextをcomment["comment"]にすればいけるか？
            #そしてSATDならもう１つのリスト変数に移す動作を行う，と言った感じになるか．
            #print "..."
            for i in range(0,value): #0~99.ただし１００個入ってない場合の処理も必要．
                if i != 299 and i >= list_len:
                    print "list end at:" + str(i)
                    break
                #if stdout == '>SATD\n>': #
                elif "Not SATD" in strlist[i]:
                    pass
                elif "SATD" in strlist[i]:
                    result.append(temp_list[i])
                    SATDComments = SATDComments + 1
                else:
                    print "WHY????"
                id2 += 1
            temp_list = [] #１００個ごとに持ってきてた情報の消去．
            string = ""
            print "SATD found = " + str(SATDComments)
        else: #value回の節目以外はパス．
            pass
        id += 1 # commentごとのforループここまで
    
    return result

#異なるリビジョンの同一コメントを消す．
#やり方：resultリストに１つずつ要素を突っ込む．
#その際，resultリストの各要素見て，comment一致，ファイル名一致，SHA不一致の３条件を満たしていたら中断し，appendしない．
#通常版と比べ，SHAを条件から取り除いている．加えて，同じものが見つかった時，last_SHAを更新している．
def samecheck(list, list2): #list = そのリビジョンのコメント，list2 = その前までのリビジョンのコメント
    result = list2
    judge = True #同一のSATDを発見したらFalseにする．
    length = len(list) #いらないかも
    print "found comments = " + str(len(list))
    for x in range(len(list)): #そのリビジョンのコメントそれぞれについて
        #print x
        for y in range(len(result)): #その前までのリビジョンのコメントと比較する．
            #でかいデータならlen(list2)ではなくlen(result)にすべし．
            if list[x]["comment"] == result[y]["comment"] and list[x]["now_filename"] == result[y]["now_filename"]:
                #print "found same SATD"
                judge = False
                result[y]["last_SHA"] = list[x]["SHA"] #ここ追加しました
                break
        if judge == True:
            result.append(list[x])
        else:
            judge = True
    print "unique comments = " + str(len(result))
    return result


#============================================================================
# original
#============================================================================




def dir_calc(proj, id): #パッチIDに応じて保存先を計算する．最後はスラッシュ付き．
    id = int(id)
    ceil1 = int(math.ceil(id/10000.0)) #math.ceil() ..切り上げ
    ceil2 = int(math.ceil(id/200.0))
    a = (ceil1 - 1) * 10000 +1
    b = (ceil1) * 10000
    c = (ceil2 - 1) * 200 +1
    d = (ceil2) * 200
    #print id
    #print ceil1
    #print ceil2
    #print a
    #print b
    #print c
    #print d
    string = './result/' + proj_name + '/' + str(a) + '-' + str(b) + '/' + str(c) + '-' + str(d) + '/' + str(id) + '/'
    return string

def api_get(script): #引数を実行し，初めの)]}'を抜いた文字列を返します．
    input = subprocess.check_output(script, shell=True, cwd='./')
    #inputから")]}'"を除外する．
    input = input.replace(")]}'\n", "", 1)
    return input

def write_read(input, path): #指定パスに書き込みを行い，さらに読み込んで辞書を返り値に取る
    with open(path, 'w') as f:
        f.write(input)
    with open(path, 'r') as h:
        #ここからjson->辞書形式で当該ファイルを読み込み
        dic = json.load(h)
    return dic

def url_encode(string): #urlエンコード．スラッシュを%2Fに変えます．
    string = string.replace("/", "%2F")
    string = string.replace("#", "%23")
    string = string.replace(" ", "%20")
    return string

def url_decode(string): #urlデコード．%2Fをスラッシュに変えます．
    string = string.replace("%2F", "/")
    string = string.replace("%23", "#")
    string = string.replace("%20", " ")
    return string

''' #一旦ストップ．perl側を変えたほうがいい
def getBlamedata(string): #blame出力から日付，時間，コードデータを取る
    #blameの形式:"SHA7桁 (commiter yyyy-mm-dd hh:mm:ss timediff line)    code"って感じ
    pattern = "([0-9]{4}\-[0-9]{2}\-[0-9]{2}) ([0-9]{2}\:[0-9]{2}\:[0-9]{2})"
    m = re.search(string, pattern)
    date = m.group(1) #1番目から．ちなみに0番目は一致部分全体を返す
    time = m.group(2)
    string.replace(m, "")
    
    #pattern = "\((.+)(\s{4}[0-9]+\)\s+)(.+)(\n)"
    pattern = "\((.+)(\s+[0-9]+\)\s+)(.+)(\n)"
    m = re.search(string, pattern)
    date = m.group(1) #1番目から．ちなみに0番目は一致部分全体を返す
    time = m.group(2)
    
'''

'''
def RQ5body(json_data): #もうperl呼ぶのめんどくさいのでこっちで作っていいっすか？
    #1.pathを変換
    #json_data["now_filename"] = #もうやってた
    #2
'''

def data_set(number, sha, file_path, comment, l_line, change_id): #file_pathは./から始まってる
    #0. git checkout(余計な手だった）
    #1.該当するファイルでコメントとの一致部分を検索
    #もしかしたら「""」->「"」に戻す必要があるかもしれない．ついでにunicode_decodeもいるかも
    #2.一致部分で最初に＋がある行をblame行として扱う
    start_line = int(l_line)
    end_line = int(l_line) #多分不要だと思うので
    now_filename = file_path.replace('./result/' + sub_name + '/', '', 1)
    #3.git blameで混入者・その時間を出す
    #これ以降はperl呼び出しで．jsonデータはsenderで．
    json_data = {"proj_name":sub_name, "pass":file_path, "comment":comment, "start_line":start_line, "end_line":end_line, "SHA":sha, "change_id":change_id, "now_filename":now_filename}
    #json_data = json.dumps(json_data)
    sender_list.append(json_data)
#    with open('./temp/sender.json', 'a') as f:
#        f.write(json_data)

        
    #文字数制限に引っかかる場合はtxtファイルに突っ込むなりする
def remove_detect(mode): #file_pathは./から始まってる
    #mode...レビュー中に追加されたSATDならmode1,レビュー開始時に追加されたSATDならmode2とする．(文字列)
    command = "perl ./srca/remove_detect.pl " + sub_name + " " + mode + " > ./temp/" + sub_name + ".log 2>&1"
    
    pipe = subprocess.call(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    #script = "git blame -l -L " + str(start_line) + ',+1 ' + hash + '--"' + file_path + '"'
    #string = subprocess.check_output(script)
    #getBlamedata(string)
    #4.git blame --reverseで同様の情報を出す
    #5.git logで除去時期・人物を求める
    #6.unixtimeで日数単位に換算する
    #7.csvに出力を行う
    
    
        
###################################################################################
###################################################################################
###################################################################################
#保存形式は？
#レビューのプロジェクト情報.. リストでプロジェクト名を保存させるのはメモリオーバーが考えられるから賢明でないと思う．
#
#openstackのgerritname .. review.opendev.org
#qt .. codereview.qt-project.org
'''
if sys.argv >= 2: #プログラム名の後に引数としてプロジェクト名があるなら
    argvs = sys.argv
    proj_name = argvs[1]
#proj_nameは団体名も含めてとる．例：openstack/もちゃんと入れる．
'''


#必要ディレクトリの準備
now_end = 673199 #qt=263350


proj_name = "openstack"
sub_name = "nova"
lang = "py"

if len(sys.argv) >= 3: #プログラム名の後に引数があるなら(argvはプログラム名も数に含めている)
    argvs = sys.argv
    proj_name = argvs[1]
    sub_name = argvs[2]
    ignore = 0
    if len(sys.argv) >= 4:
        ignore = argvs[3] #引数に値が存在すれば，その分だけすでに終わってることにする
else:
    raise HikisuTarinaiError

#number = ignore #number..現在見ているレビューidのこと．


if proj_name == "openstack":
    address = "review.opendev.org" #address..プロジェクトによる固有ドメイン
    now_end = 673199 #qt=263350
if proj_name == "qt":
    address = "codereview.qt-project.org"
    now_end = 263350



#number = int(number) #文字列ー＞数値

#with open('./dict/result_' + sub_name + 'nova.json', 'r') as g:
#    json_dic = json.load(g)

list_count = 0 #進捗表示用変数
list_length = 0
error_ids = [] #checkoutに失敗したIDを格納する．
sent_count = 0 #実際に該当するデータ

#number...レビューナンバー


#先ずはcsvファイルを読み込め.未作成の可能性もある.
csv_path_list = ['./data/result_RQ4_comments_' + sub_name + '.csv', './data/result_add_unreview_' + sub_name + '.csv']

rtn = checkout("master")
if rtn == 1:
    print "WARN:base branch is not master!!!"

with open('./data/RQ5_' + sub_name + '.csv', 'w+') as f:
    input = "PROJ,Introduce_ID,Remove_ID,FILE,PASS,startLINE,endLINE,Intro_DATE,TIME,timediff,Remove_DATE,TIME,timediff,Intro_author,Remove_author,COMMENT,Last_found_id,survive,removed,same\n"
    f.write(input)

with open('./data/rejected_list_' + sub_name + '.json', 'r') as f:
    rejected_dict = json.load(f)



for i, csv_path in enumerate(csv_path_list): #すり抜けた方のみ取りたい等の場合はcsv_path_listをいじって
    sender_list = []
    if i == 0:
        open_path = './data/RQ5_' + sub_name + '.csv'
    elif i == 1:
        open_path = './data/RQ5-2_' + sub_name + '.csv'
    
    with open(csv_path, 'r') as f:
      r = csv.reader(f)
      reader = [row for row in r] #２次元リスト化
        #何とかして読み込ませてsplitline

    #with open('./temp/sender.json', 'w+') as f:
    #    f.write('[')
    #for number in json_dic["SATD_have"]:
    list_length += len(reader)-1
    for row in reader[1:]:
        list_count += 1
        number = row[0]
        if int(number) < int(ignore): #途中から始めたいとき用
            continue
        skip_flag = False
        
        #numberがrejected_listに存在したら(mergeされてないものなら)飛ばす！
        if int(number) in rejected_dict["rejected_list"]:
            continue
        
        f_path = row[1]
        patch = row[2]
        l_patch = row[3] #last_found_patchの略です．わかりにくいけど．
        total_patch = row[4]
        line = row[5]
        l_line = row[6]
        change_id = row[7]
        comment = row[8]
        print "now number = " + str(number)
        print "now:" + str(list_count) +"/"+ str(list_length)
        #ここでl_found_patch>=p_endであるかをチェックする．否ならマージ時に既に消えてるSATDなのでcontinue
        if int(l_patch) < int(total_patch):
            continue
        
        #remove_detect ... current_revision, start_line
        
        #script = 'curl "https://'+ address +'/changes/?q=' + str(number) + '&o=CURRENT_REVISION"'
        #input = api_get(script)
        path = dir_calc(proj_name, number) + 'query.json'
        #with open(path, 'w') as f:
        #    f.write(input)
        with open(path, 'r') as h:
            #ここからjson->辞書形式で当該ファイルを読み込み
            dic = json.load(h)
        if not ("current_revision" in dic[0]):
            #error_ids.append(number)
            print "skipped" #NEWかABANDONEDの場合はcurrentが存在しない． #ってわけでもないらしい
            continue
        x = dic[0]["current_revision"] #出力は長さ１のリストの中に辞書が入ってるので[0]必要。
        total_patch = dic[0]["revisions"][x]["_number"] #その変更のパッチ総数．
        total_patch = int(total_patch) #パッチ総数
        #残りはひとまとめに
            
        data_set(number, x, f_path, comment, l_line, change_id)
        
        sent_count += 1
        
    with open('./temp/sender_' + sub_name + '.json', 'w') as f:
        #f.write(']')
        #f.write(sender_list)
        json.dump(sender_list, f)
    if i == 0:
        remove_detect("mode1")
    elif i == 1:
        remove_detect("mode2")
        
        
    '''if list_count < len(reader) - 1 :
        with open('./temp/sender.json', 'a') as f:
            f.write(',')
    else:
        pass'''
    



print "sent_count = " + str(sent_count)
#sent_countをどこかに保存したい
with open('./data/RQ5_sent_info_' + sub_name + '.json', 'w') as f:
    count_json = {"sent_count":sent_count}
    json.dump(count_json, f)
print "finish!"

#パッチの数の取り方．．currentで取ってjsonに変換した後に値を取得しカウントダウン式に取る？

#レビューコメントの取り方
#while patch <= total_patch: #各パッチについてコメントとレビューの情報を取る
    #script = 'curl "https://'+ address +'/changes/' + str(number) + '/revisions/' + str(patch) + '/comments"'