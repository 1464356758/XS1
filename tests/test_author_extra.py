"""只在临时合成小说中验证作者手动加更，不调用任何外部服务。"""
import json
from datetime import datetime,timedelta
from unittest.mock import patch
import test_daily_update as fixtures
from test_novel_state import WorkspaceFixture
daily,ns=fixtures.daily,fixtures.ns


class AuthorExtraTests(WorkspaceFixture):
    def setUp(self):
        super().setUp()
        self.project=self.root.parent
        self.serial=ns.serial_module()
        self.a=ns.serial_api()
        self.serial.enable(self.root,'合成测试启用',ns.load_state(self.root)['revision'],self.a)
    prepare=fixtures.DailyTests.prepare
    gate=fixtures.DailyTests.gate
    release=fixtures.DailyTests.release
    def authorize(self, name='next.json'):
        state=ns.load_state(self.root);n=len(state['chapters'])+1
        path='author_requests/'+name
        data={'book_id':state['book_id'],'source':'current_user_message','request':'下一章',
              'chapter':n,'baseline_count':n-1,'baseline_fingerprint':daily.prefix_fingerprint(state,n-1),
              'base_revision':state['revision'],'received_at':daily.stamp()}
        ns.atomic_json(self.root/path,data)
        return path

    def first(self):
        task=daily.begin(self.project);self.release(1);receipt=daily.finish(self.project,task['run_id'])
        return receipt,(self.root/'daily'/f"{receipt['date']}.json").read_bytes()

    def test_explicit_extra_preserves_daily_receipt_and_frozen_prefix(self):
        first,old=self.first();prefix=ns.load_state(self.root)['chapters']['1'].copy()
        task=daily.begin(self.project,author_request=self.authorize())
        self.assertEqual(task['chapter'],2);self.assertNotEqual(task['run_id'],first['run_id'])
        self.release(2);receipt=daily.finish(self.project,task['run_id'])
        self.assertEqual((self.root/'daily'/f"{first['date']}.json").read_bytes(),old)
        active=daily.active_record(self.root);self.assertTrue(active['receipt_path'].startswith('daily/extra/'))
        self.assertEqual(daily.verify_receipt(self.root,ns.load_state(self.root),receipt)['chapter'],2)
        self.assertEqual(ns.load_state(self.root)['chapters']['1'],prefix)
        self.assertEqual(daily.begin(self.project)['action'],'already_completed')
        self.assertEqual(daily.begin(self.project)['chapter'],2)
        self.assertEqual(daily.finish(self.project,task['run_id'])['body_sha256'],receipt['body_sha256'])

    def test_stale_request_cannot_advance_another_chapter(self):
        self.first();path=self.authorize();task=daily.begin(self.project,author_request=path)
        self.release(2);daily.finish(self.project,task['run_id'])
        with self.assertRaises(daily.ns.WorkspaceError):daily.begin(self.project,author_request=path)
        self.assertEqual(daily.active_record(self.root)['chapter'],2)

    def test_new_author_request_does_not_steal_running_target(self):
        self.first();task=daily.begin(self.project,author_request=self.authorize())
        again=daily.begin(self.project,author_request=self.authorize('new.json'))
        self.assertEqual(again['action'],'verify_in_progress');self.assertEqual(again['run_id'],task['run_id'])
        self.assertEqual(daily.begin(self.project)['action'],'verify_in_progress')

    def test_request_identity_and_prefix_are_checked_before_begin(self):
        self.first()
        for change in ({'book_id':'other'},{'chapter':3},{'baseline_fingerprint':'0'*64},{'source':'scheduled_prompt'}):
            path=self.authorize();d=ns.read_json(self.root/path);d.update(change);ns.atomic_json(self.root/path,d)
            with self.assertRaises(daily.ns.WorkspaceError):daily.begin(self.project,author_request=path)
        self.assertEqual(daily.active_record(self.root)['chapter'],1)

    def test_changed_author_file_blocks_finish(self):
        self.first();path=self.authorize();task=daily.begin(self.project,author_request=path)
        self.release(2);d=ns.read_json(self.root/path);d['request']='自动执行';ns.atomic_json(self.root/path,d)
        with self.assertRaises(daily.ns.WorkspaceError):daily.finish(self.project,task['run_id'])

    def test_extra_receipt_recovery_is_not_a_new_target(self):
        self.first();task=daily.begin(self.project,author_request=self.authorize());self.release(2)
        daily.finish(self.project,task['run_id']);active=daily.active_record(self.root)
        (self.root/active['receipt_path']).unlink()
        result=daily.begin(self.project,author_request=self.authorize('third.json'))
        self.assertEqual(result['action'],'recovered_completion');self.assertEqual(result['chapter'],2)
        self.assertEqual(daily.active_record(self.root)['run_id'],task['run_id'])

    def test_next_day_default_continues_after_extra(self):
        self.first();task=daily.begin(self.project,author_request=self.authorize());self.release(2)
        receipt=daily.finish(self.project,task['run_id'])
        tomorrow=(datetime.fromisoformat(receipt['completed_at'])+timedelta(days=1)).isoformat()
        with patch.object(daily,'stamp',return_value=tomorrow):self.assertEqual(daily.begin(self.project)['chapter'],3)

    def test_naive_author_time_is_rejected(self):
        self.first();path=self.authorize();d=ns.read_json(self.root/path);d['received_at']='2026-01-01T01:00:00';ns.atomic_json(self.root/path,d)
        with self.assertRaises(daily.ns.WorkspaceError):daily.begin(self.project,author_request=path)
